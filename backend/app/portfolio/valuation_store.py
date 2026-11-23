import sqlite3
from contextlib import closing
from pathlib import Path

from .models import PortfolioSnapshot
from .valuation import ValuationSnapshot


class ValuationSnapshotStore:
    """Guarda snapshots inmutables de tenencias y valoraciones en SQLite."""

    def __init__(self, path: Path):
        self.path = path
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS multiactive_portfolios (
                    portfolio_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (portfolio_id, version)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS valuation_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def save_portfolio(self, portfolio: PortfolioSnapshot) -> None:
        key = (portfolio.portfolio_id, portfolio.version)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO multiactive_portfolios (portfolio_id, version, payload)
                VALUES (?, ?, ?) ON CONFLICT(portfolio_id, version) DO NOTHING
                """,
                (*key, portfolio.model_dump_json()),
            )
            row = connection.execute(
                "SELECT payload FROM multiactive_portfolios WHERE portfolio_id = ? AND version = ?",
                key,
            ).fetchone()
            if PortfolioSnapshot.model_validate_json(row[0]) != portfolio:
                raise ValueError(f"portfolio version already used: {key}")

    def latest_portfolio(self, portfolio_id: str) -> PortfolioSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT payload FROM multiactive_portfolios WHERE portfolio_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (portfolio_id,),
            ).fetchone()
        return PortfolioSnapshot.model_validate_json(row[0]) if row else None

    def save(self, snapshot: ValuationSnapshot) -> None:
        payload = snapshot.model_dump_json()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO valuation_snapshots (snapshot_id, payload) VALUES (?, ?)
                ON CONFLICT(snapshot_id) DO NOTHING
                """,
                (snapshot.snapshot_id, payload),
            )
            existing = connection.execute(
                "SELECT payload FROM valuation_snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if existing != (payload,):
                raise ValueError(f"valuation snapshot id already used: {snapshot.snapshot_id}")

    def get(self, snapshot_id: str) -> ValuationSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM valuation_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return ValuationSnapshot.model_validate_json(row[0]) if row else None

    def latest_for_portfolio(self, portfolio: PortfolioSnapshot) -> ValuationSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT payload FROM valuation_snapshots
                WHERE json_extract(payload, '$.portfolio_id') = ?
                  AND json_extract(payload, '$.portfolio_version') = ?
                  AND json_extract(payload, '$.portfolio_snapshot_id') = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (portfolio.portfolio_id, portfolio.version, portfolio.snapshot_id),
            ).fetchone()
        return ValuationSnapshot.model_validate_json(row[0]) if row else None
