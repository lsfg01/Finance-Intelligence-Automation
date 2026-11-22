"""Persistencia sencilla de demo. Un worker, SQLite local, sin autenticacion."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .fixtures import DEMO_PORTFOLIO, DEMO_PROFILE, DEMO_DOCUMENT
from .models import Portfolio, Profile, SourceDocument
from .analysis import build_report


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path() -> str:
    return os.environ.get("DB_PATH", ".local/portfolio.sqlite3")


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def init_db(path: str) -> None:
    with connect(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS portfolio_versions (
                version INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profile_versions (
                version INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                portfolio_version INTEGER NOT NULL,
                profile_version INTEGER NOT NULL,
                documents_json TEXT NOT NULL,
                error TEXT,
                report_id TEXT
            );
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                portfolio_version INTEGER NOT NULL,
                profile_version INTEGER NOT NULL,
                portfolio_snapshot_json TEXT NOT NULL,
                profile_snapshot_json TEXT NOT NULL,
                documents_snapshot_json TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
        """)
        if conn.execute("SELECT COUNT(*) FROM portfolio_versions").fetchone()[0] == 0:
            conn.execute("INSERT INTO portfolio_versions(created_at,payload_json) VALUES(?,?)",
                         (utcnow(), DEMO_PORTFOLIO.model_dump_json()))
        if conn.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0] == 0:
            conn.execute("INSERT INTO profile_versions(created_at,payload_json) VALUES(?,?)",
                         (utcnow(), DEMO_PROFILE.model_dump_json()))
        conn.execute("INSERT OR IGNORE INTO documents(id,payload_json) VALUES(?,?)",
                     (DEMO_DOCUMENT.document_id, DEMO_DOCUMENT.model_dump_json()))


def latest_version(path: str, table: str) -> dict:
    if table not in ("portfolio_versions", "profile_versions"):
        raise ValueError("Tabla no permitida")
    with connect(path) as conn:
        row = conn.execute(f"SELECT version,created_at,payload_json FROM {table} ORDER BY version DESC LIMIT 1").fetchone()
        if row is None:
            raise RuntimeError("Base sin inicializar")
        return {"version": row["version"], "created_at": row["created_at"], "data": json.loads(row["payload_json"])}


def save_version(path: str, table: str, payload: Portfolio | Profile) -> dict:
    if table not in ("portfolio_versions", "profile_versions"):
        raise ValueError("Tabla no permitida")
    with connect(path) as conn:
        cur = conn.execute(f"INSERT INTO {table}(created_at,payload_json) VALUES(?,?)",
                           (utcnow(), payload.model_dump_json()))
        return {"version": cur.lastrowid, "data": payload.model_dump(mode="json")}


def create_run(path: str) -> dict:
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pv = conn.execute("SELECT version FROM portfolio_versions ORDER BY version DESC LIMIT 1").fetchone()[0]
        pf = conn.execute("SELECT version FROM profile_versions ORDER BY version DESC LIMIT 1").fetchone()[0]
        docs = [json.loads(r["payload_json"]) for r in conn.execute("SELECT payload_json FROM documents ORDER BY id")]
        run_id = str(uuid.uuid4())
        now = utcnow()
        conn.execute("""INSERT INTO analysis_runs(id,status,created_at,updated_at,portfolio_version,
                     profile_version,documents_json) VALUES(?,?,?,?,?,?,?)""",
                     (run_id, "queued", now, now, pv, pf, to_json(docs)))
        return {"id": run_id, "status": "queued", "portfolio_version": pv, "profile_version": pf}


def get_run(path: str, run_id: str) -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM analysis_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    return {k: row[k] for k in ("id", "status", "created_at", "updated_at", "portfolio_version",
                                 "profile_version", "error", "report_id")}


def list_reports(path: str) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute("""SELECT id,created_at,portfolio_version,profile_version
                               FROM reports ORDER BY created_at DESC""").fetchall()
    return [dict(x) for x in rows]


def get_report(path: str, report_id: str) -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "created_at": row["created_at"],
            "portfolio_version": row["portfolio_version"], "profile_version": row["profile_version"],
            "input_snapshot": {
                "portfolio": json.loads(row["portfolio_snapshot_json"]),
                "profile": json.loads(row["profile_snapshot_json"]),
                "documents": json.loads(row["documents_snapshot_json"])
            }, "result": json.loads(row["payload_json"])}


def process_one(path: str) -> str | None:
    """Reclama un trabajo bajo bloqueo y guarda un informe inmutable. Un worker de demo."""
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM analysis_runs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        run_id = row["id"]
        conn.execute("UPDATE analysis_runs SET status='running',updated_at=? WHERE id=? AND status='queued'",
                     (utcnow(), run_id))
    try:
        with connect(path) as conn:
            p_row = conn.execute("SELECT payload_json FROM portfolio_versions WHERE version=?",
                                 (row["portfolio_version"],)).fetchone()
            f_row = conn.execute("SELECT payload_json FROM profile_versions WHERE version=?",
                                 (row["profile_version"],)).fetchone()
        portfolio_json = p_row["payload_json"]
        profile_json = f_row["payload_json"]
        docs_json = row["documents_json"]
        report = build_report(Portfolio.model_validate_json(portfolio_json),
                              Profile.model_validate_json(profile_json),
                              [SourceDocument.model_validate(d) for d in json.loads(docs_json)])
        report_id = str(uuid.uuid4())
        with connect(path) as conn:
            conn.execute("""INSERT INTO reports(id,created_at,portfolio_version,profile_version,
                         portfolio_snapshot_json,profile_snapshot_json,documents_snapshot_json,payload_json)
                         VALUES(?,?,?,?,?,?,?,?)""",
                         (report_id, utcnow(), row["portfolio_version"], row["profile_version"],
                          portfolio_json, profile_json, docs_json, to_json(report)))
            conn.execute("UPDATE analysis_runs SET status='completed',report_id=?,updated_at=? WHERE id=?",
                         (report_id, utcnow(), run_id))
    except Exception as exc:
        with connect(path) as conn:
            conn.execute("UPDATE analysis_runs SET status='failed',error=?,updated_at=? WHERE id=?",
                         (str(exc)[:1000], utcnow(), run_id))
    return run_id
