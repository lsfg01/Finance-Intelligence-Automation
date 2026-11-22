import sqlite3
from contextlib import closing
from pathlib import Path

from .valuation import ValuationSnapshot


class ValuationSnapshotStore:
    """Guarda snapshots de valoración inmutables en una tabla SQLite propia."""

    def __init__(self, path: Path):
        self.path = path
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS valuation_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

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

    def latest_for_portfolio(self, portfolio_id: str) -> ValuationSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT payload FROM valuation_snapshots
                WHERE json_extract(payload, '$.portfolio_id') = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (portfolio_id,),
            ).fetchone()
        return ValuationSnapshot.model_validate_json(row[0]) if row else None
