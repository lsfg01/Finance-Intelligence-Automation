from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from . import db
from .models import Portfolio, Profile
from .portfolio.routes import valuation_router

def frontend_path() -> Path:
    """Use an explicit path in a container; retain local editable-install support."""
    default_path = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    return Path(os.environ.get("FRONTEND_PATH", str(default_path)))


def create_app(database_path: str | None = None) -> FastAPI:
    path = database_path or db.db_path()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db(path)
        yield

    app = FastAPI(title="Analisis de inversiones - demo", version="0.1.0", lifespan=lifespan)
    app.include_router(valuation_router(Path(path)))

    @app.get("/")
    def home():
        return FileResponse(frontend_path())

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "offline_demo", "model_calls": 0}

    @app.get("/api/portfolio")
    def get_portfolio():
        return db.latest_version(path, "portfolio_versions")

    @app.put("/api/portfolio")
    def update_portfolio(payload: Portfolio):
        return db.save_version(path, "portfolio_versions", payload)

    @app.get("/api/profile")
    def get_profile():
        return db.latest_version(path, "profile_versions")

    @app.put("/api/profile")
    def update_profile(payload: Profile):
        return db.save_version(path, "profile_versions", payload)

    @app.post("/api/analyses", status_code=status.HTTP_202_ACCEPTED)
    def create_analysis():
        return db.create_run(path)

    @app.get("/api/analyses/{run_id}")
    def get_analysis(run_id: str):
        run = db.get_run(path, run_id)
        if not run:
            raise HTTPException(404, "Trabajo no encontrado")
        return run

    @app.get("/api/reports")
    def list_reports():
        return db.list_reports(path)

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: str):
        report = db.get_report(path, report_id)
        if not report:
            raise HTTPException(404, "Informe no encontrado")
        return report

    return app


app = create_app()
