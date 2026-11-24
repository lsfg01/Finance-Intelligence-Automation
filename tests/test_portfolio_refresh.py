import sqlite3
from contextlib import closing
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from app.models import Portfolio
from app.portfolio.fixtures import DEMO_PORTFOLIO
from app.portfolio.valuation import ValuationSnapshot
from app.portfolio.valuation_store import ValuationSnapshotStore


def test_dashboard_refresh_persists_a_partial_valuation_without_creating_an_analysis(tmp_path, monkeypatch):
    path = tmp_path / "demo.sqlite3"

    def unexpected_market_call(*args, **kwargs):
        raise AssertionError("Unexpected market request")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_market_call)
    monkeypatch.delenv("ENABLE_LIVE_MARKET_DATA", raising=False)
    with TestClient(create_app(str(path))) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="refresh-prices">Actualizar precios' in page.text
        assert 'id="run">Analizar cartera' in page.text
        initial = client.get("/api/portfolio/valuation").json()
        assert initial["portfolio"] == DEMO_PORTFOLIO.model_dump(mode="json")
        assert len(initial["portfolio"]["positions"]) == 11
        assert initial["valuation"] is None
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM valuation_snapshots").fetchone() == (0,)
            assert connection.execute("SELECT COUNT(*) FROM analysis_runs").fetchone() == (0,)

        response = client.post("/api/portfolio/refresh-prices")
        assert response.status_code == 201
        assert response.json()["portfolio"] == initial["portfolio"]
        assert response.json()["valuation_mode"] == "simulated"
        valuation = response.json()["valuation"]
        assert [row["position"] for row in valuation["positions"]] == initial["portfolio"]["positions"]
        assert UUID(valuation["snapshot_id"])
        assert valuation["status"] == "PARTIAL"
        assert valuation["total_value"] is None
        assert valuation["valued_positions"] == 10
        assert valuation["total_positions"] == 11
        assert valuation["is_simulated"]
        assert valuation["as_of"] == "2024-01-15"
        assert Decimal(valuation["known_value"]) > 0
        assert {item["retrieved_at"] for item in valuation["price_observations"]} == {"2024-01-15T22:00:00Z"}
        missing = [row for row in valuation["positions"] if row["issue"] == "MISSING_PRICE"]
        assert [row["position"]["instrument_id"] for row in missing] == ["F04"]
        assert client.get("/api/portfolio/valuation").json() == response.json()
        assert client.get("/api/reports").json() == []
        assert db.process_one(str(path)) is None

    with TestClient(create_app(str(path))) as restarted:
        assert restarted.get("/api/portfolio/valuation").json() == response.json()
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM multiactive_portfolios").fetchone() == (1,)


def test_refresh_preserves_holdings_previous_valuation_and_report(tmp_path, monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "mock")
    path = tmp_path / "demo.sqlite3"
    db.init_db(str(path))
    legacy = db.latest_version(str(path), "portfolio_versions")
    edited = Portfolio.model_validate(legacy["data"]).model_copy(update={"name": "Cartera editada"})
    db.save_version(str(path), "portfolio_versions", edited)
    run = db.create_run(str(path))
    assert db.process_one(str(path)) == run["id"]
    report_id = db.get_run(str(path), run["id"])["report_id"]
    original_report = db.get_report(str(path), report_id)
    envelope = original_report["result"]["intelligence"]
    assert envelope["result"]["implementation"] == "mock"
    assert envelope["context"]["portfolio"]["name"] == "Cartera editada"
    with TestClient(create_app(str(path))) as client:
        original_portfolio = client.get("/api/portfolio").json()
        assert original_portfolio["data"]["name"] == "Cartera editada"
        assert client.get("/api/portfolio/valuation").json()["portfolio"]["positions"]
        first = client.post("/api/portfolio/refresh-prices?mode=simulated").json()["valuation"]
        second = client.post("/api/portfolio/refresh-prices?mode=simulated").json()["valuation"]

        assert first["snapshot_id"] != second["snapshot_id"]
        assert first["portfolio_snapshot_id"] == second["portfolio_snapshot_id"]
        assert first["positions"] == second["positions"]
        assert client.get("/api/portfolio/valuation").json()["valuation"] == second
        assert client.get("/api/portfolio").json() == original_portfolio
        assert client.get(f"/api/reports/{report_id}").json() == original_report
        assert db.process_one(str(path)) is None

        stored = ValuationSnapshotStore(path).get(first["snapshot_id"])
        assert stored is not None
        assert stored.model_dump(mode="json") == first


def test_valuation_is_only_reused_for_the_active_portfolio_version(tmp_path):
    path = tmp_path / "demo.sqlite3"
    with TestClient(create_app(str(path))) as client:
        first = client.post("/api/portfolio/refresh-prices?mode=simulated").json()["valuation"]

    store = ValuationSnapshotStore(path)
    updated_position = DEMO_PORTFOLIO.positions[0].model_copy(update={"quantity": Decimal("12")})
    updated = DEMO_PORTFOLIO.model_copy(update={
        "version": 2,
        "snapshot_id": "SIM-SNAPSHOT-2",
        "positions": (updated_position, *DEMO_PORTFOLIO.positions[1:]),
    })
    store.save_portfolio(updated)
    with TestClient(create_app(str(path))) as client:
        initial = client.get("/api/portfolio/valuation").json()
        assert initial["portfolio"] == updated.model_dump(mode="json")
        assert initial["valuation"] is None
        refreshed = client.post("/api/portfolio/refresh-prices?mode=simulated").json()
        assert refreshed["valuation"]["portfolio_snapshot_id"] == updated.snapshot_id
        assert refreshed["valuation"]["portfolio_version"] == updated.version
        assert refreshed["valuation"]["positions"][0]["position"]["quantity"] == "12"
        assert store.get(first["snapshot_id"]).model_dump(mode="json") == first


def test_valuation_from_before_mode_tracking_is_still_labeled(tmp_path):
    with TestClient(create_app(str(tmp_path / "source.sqlite3"))) as client:
        original = client.post("/api/portfolio/refresh-prices?mode=simulated").json()

    path = tmp_path / "legacy.sqlite3"
    ValuationSnapshotStore(path).save(ValuationSnapshot.model_validate(original["valuation"]))
    with TestClient(create_app(str(path))) as client:
        assert client.get("/api/portfolio/valuation").json() == original


def test_live_refresh_returns_explicit_error_and_creates_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("EODHD_API_TOKEN", "test-only")
    monkeypatch.delenv("ENABLE_LIVE_MARKET_DATA", raising=False)
    with TestClient(create_app(str(tmp_path / "demo.sqlite3"))) as client:
        response = client.post("/api/portfolio/refresh-prices?mode=live")
        assert response.status_code == 503
        assert response.json() == {"detail": "Sin proveedor autorizado de precios reales"}
        assert client.get("/api/portfolio/valuation").json()["valuation"] is None
        monkeypatch.setenv("ENABLE_LIVE_MARKET_DATA", "1")
        monkeypatch.delenv("EODHD_API_TOKEN")
        assert client.post("/api/portfolio/refresh-prices?mode=live").status_code == 503
        auto = client.post("/api/portfolio/refresh-prices")
        assert auto.status_code == 503
        assert auto.json()["detail"] == "Falta configurar EODHD_API_TOKEN"
        assert client.get("/api/portfolio/valuation").json()["valuation"] is None
