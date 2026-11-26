import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from .holdings import HoldingsSource, InvestingExport
from .import_valuation import ImportedValuation, value_import
from .models import PortfolioSnapshot
from .valuation import ValuationSnapshot


PriceMode = Literal["simulated", "live", "imported"]


class PortfolioVersionChanged(Exception):
    pass


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
                CREATE TABLE IF NOT EXISTS holdings_sources (
                    snapshot_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS investing_imports (
                    portfolio_snapshot_id TEXT PRIMARY KEY,
                    valuation_id TEXT NOT NULL UNIQUE,
                    digest TEXT NOT NULL,
                    payload TEXT NOT NULL
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS valuation_snapshot_modes (
                    snapshot_id TEXT PRIMARY KEY REFERENCES valuation_snapshots(snapshot_id),
                    mode TEXT NOT NULL CHECK (mode IN ('simulated', 'live'))
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

    def portfolio_version(self, portfolio_id: str, version: int) -> PortfolioSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM multiactive_portfolios WHERE portfolio_id = ? AND version = ?",
                (portfolio_id, version),
            ).fetchone()
        return PortfolioSnapshot.model_validate_json(row[0]) if row else None

    def list_portfolios(self) -> tuple[PortfolioSnapshot, ...]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                """
                SELECT p.payload FROM multiactive_portfolios p
                JOIN (
                    SELECT portfolio_id, MAX(version) AS version, MIN(rowid) AS first_row
                    FROM multiactive_portfolios GROUP BY portfolio_id
                ) latest USING (portfolio_id, version)
                ORDER BY latest.first_row
                """
            ).fetchall()
        return tuple(PortfolioSnapshot.model_validate_json(row[0]) for row in rows)

    def get_source(self, snapshot_id: str) -> HoldingsSource | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM holdings_sources WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
        return HoldingsSource.model_validate_json(row[0]) if row else None

    def get_import(self, snapshot_id: str) -> ImportedValuation | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM investing_imports WHERE portfolio_snapshot_id = ?", (snapshot_id,),
            ).fetchone()
        return ImportedValuation.model_validate_json(row[0]) if row else None

    def save_loaded_portfolio(
        self, portfolio: PortfolioSnapshot, source: HoldingsSource, *, expected_version: int,
        export: InvestingExport | None = None, digest: str | None = None,
    ) -> PortfolioSnapshot:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                """
                SELECT p.version, p.payload, i.digest FROM multiactive_portfolios p
                LEFT JOIN investing_imports i ON i.portfolio_snapshot_id = json_extract(p.payload, '$.snapshot_id')
                WHERE p.portfolio_id = ? ORDER BY p.version DESC LIMIT 1
                """,
                (portfolio.portfolio_id,),
            ).fetchone()
            version = latest[0] if latest else 0
            if latest and digest is not None and latest[2] == digest:
                return PortfolioSnapshot.model_validate_json(latest[1])
            if version != expected_version:
                raise PortfolioVersionChanged
            portfolio = portfolio.model_copy(update={"version": version + 1})
            connection.execute(
                "INSERT INTO multiactive_portfolios (portfolio_id, version, payload) VALUES (?, ?, ?)",
                (portfolio.portfolio_id, portfolio.version, portfolio.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO holdings_sources (snapshot_id, payload) VALUES (?, ?)",
                (portfolio.snapshot_id, source.model_dump_json()),
            )
            if export is not None:
                valuation, imported = value_import(portfolio, export, source.loaded_at)
                connection.execute(
                    "INSERT INTO valuation_snapshots (snapshot_id, payload) VALUES (?, ?)",
                    (valuation.snapshot_id, valuation.model_dump_json()),
                )
                connection.execute(
                    "INSERT INTO investing_imports VALUES (?, ?, ?, ?)",
                    (portfolio.snapshot_id, valuation.snapshot_id, digest, imported.model_dump_json()),
                )
        return portfolio

    def save(self, snapshot: ValuationSnapshot, *, mode: Literal["simulated", "live"] | None = None) -> None:
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
            if mode is not None:
                connection.execute(
                    """
                    INSERT INTO valuation_snapshot_modes (snapshot_id, mode) VALUES (?, ?)
                    ON CONFLICT(snapshot_id) DO NOTHING
                    """,
                    (snapshot.snapshot_id, mode),
                )
                existing_mode = connection.execute(
                    "SELECT mode FROM valuation_snapshot_modes WHERE snapshot_id = ?",
                    (snapshot.snapshot_id,),
                ).fetchone()
                if existing_mode != (mode,):
                    raise ValueError(f"valuation snapshot mode already set: {snapshot.snapshot_id}")

    def get(self, snapshot_id: str) -> ValuationSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM valuation_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return ValuationSnapshot.model_validate_json(row[0]) if row else None

    def latest_for_portfolio(
        self, portfolio: PortfolioSnapshot
    ) -> tuple[ValuationSnapshot | None, PriceMode | None]:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT valuation_snapshots.payload,
                       CASE WHEN investing_imports.valuation_id IS NOT NULL THEN 'imported' ELSE mode END
                FROM valuation_snapshots
                LEFT JOIN valuation_snapshot_modes USING (snapshot_id)
                LEFT JOIN investing_imports ON investing_imports.valuation_id = valuation_snapshots.snapshot_id
                WHERE json_extract(valuation_snapshots.payload, '$.portfolio_id') = ?
                  AND json_extract(valuation_snapshots.payload, '$.portfolio_version') = ?
                  AND json_extract(valuation_snapshots.payload, '$.portfolio_snapshot_id') = ?
                ORDER BY valuation_snapshots.rowid DESC LIMIT 1
                """,
                (portfolio.portfolio_id, portfolio.version, portfolio.snapshot_id),
            ).fetchone()
        return (ValuationSnapshot.model_validate_json(row[0]), row[1]) if row else (None, None)
