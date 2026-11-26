from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.intelligence.portfolio_test import PortfolioTestInput, PortfolioTestResult, analyze_portfolio_snapshot
from app.main import create_app
from app.portfolio import refresh, routes
from app.portfolio.models import FXObservation, MarketObservation
from app.portfolio.valuation_store import ValuationSnapshotStore


PREFIX = "/api/portfolio"
FIXTURE = Path(__file__).parent / "fixtures" / "investing_holdings_demo_25112026.csv"
ACCEPTANCE_AT = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)


@pytest.fixture
def demo(tmp_path, monkeypatch):
    calls = []

    class AcceptanceClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return ACCEPTANCE_AT.astimezone(tz) if tz else ACCEPTANCE_AT.replace(tzinfo=None)

    def forbidden(*args, **kwargs):
        calls.append("market")
        raise AssertionError("Consulta de mercado fuera del refresco")

    monkeypatch.setattr(refresh, "EODHDPriceProvider", forbidden)
    monkeypatch.setattr(refresh, "ECBFXProvider", forbidden)
    monkeypatch.setattr(routes, "datetime", AcceptanceClock)
    monkeypatch.setattr(refresh, "datetime", AcceptanceClock)
    monkeypatch.setattr(db, "utcnow", lambda: ACCEPTANCE_AT.isoformat())
    monkeypatch.setenv("ENABLE_LIVE_MARKET_DATA", "1")
    monkeypatch.setenv("EODHD_API_TOKEN", "demo-placeholder")
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "mock")
    path = tmp_path / "acceptance.sqlite3"
    with TestClient(create_app(str(path))) as client:
        yield client, path
    assert calls == []


def payload(csv=None, account="Intelligence Auto Demo"):
    return {"account": account, "csv": FIXTURE.read_text(encoding="utf-8") if csv is None else csv,
            "filename": FIXTURE.name}


def preview(client, document):
    response = client.post(f"{PREFIX}/investing/preview", json=document)
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, document, token=None):
    token = token or preview(client, document)["preview_token"]
    response = client.post(f"{PREFIX}/investing/confirm", json={**document, "preview_token": token})
    assert response.status_code == 201, response.text
    return response.json()


def valuation(client, selection, **params):
    response = client.get(f"{PREFIX}/valuation", params={"portfolio_id": selection["portfolio_id"], **params})
    assert response.status_code == 200, response.text
    return response.json()


def queue(client, selection):
    response = client.post("/api/analyses", json={k: selection[k] for k in
                            ("portfolio_id", "portfolio_version", "valuation_id")})
    assert response.status_code == 202, response.text
    return response.json()


def counts(path):
    with closing(db.connect(str(path))) as conn:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("analysis_runs", "reports", "investing_imports"))


def test_a1_a2_import_prices_totals_and_coverage(demo):
    client, path = demo
    saved = confirm(client, payload())
    result = valuation(client, saved)
    assert result["valuation_mode"] == "imported"
    assert result["source"]["reference_date"] == "2026-11-25"
    assert result["source"]["reference_origin"] == "filename"
    snapshot = result["valuation"]
    assert snapshot["total_value"] is None and snapshot["valued_positions"] == 0
    assert not snapshot["fx_observations"]
    rows = result["imported"]["export"]["rows"]
    assert len(rows) == 3 and sum(len(row["lots"]) for row in rows) == 3
    assert sum(Decimal(row["quote_value"]) for row in snapshot["positions"]) == Decimal("17922.40")
    assert {row["quote_currency"] for row in snapshot["positions"]} == {"USD"}
    assert sum(Decimal(row["economics"]["weight_pct"]) for row in rows) == Decimal("100.00")
    assert sum(Decimal(row["economics"]["net_pnl"]["money"]["amount"]) for row in rows) == Decimal("19.72")
    msft = next(row for row in rows if row["label"] == "MSFT.O")
    assert msft["quantity"] == "5.00000000"
    assert msft["side"] == "long"
    assert msft["lots"][0] == {"quantity": "5.00000000", "opened_on": "2026-11-25",
                               "entry_price": {"amount": "482.43", "currency": "USD"}}
    assert msft["economics"]["current_price"] == {"amount": "483.22", "currency": "USD"}
    assert msft["economics"]["quote_time"] == "18:04:52"
    assert msft["economics"]["commission"] == {"amount": "0.00", "currency": "USD"}
    totals = result["imported"]["export"]["totals"]
    assert totals["market_value"] == {"amount": "16320.14", "currency": "EUR"}
    assert totals["open_pnl"] == {"money": {"amount": "19.71", "currency": "EUR"}, "percentage": "0.12"}
    assert totals["total_pnl"]["money"]["amount"] == "19.71"
    with TestClient(create_app(str(path))) as restarted:
        assert valuation(restarted, saved) == result

    text = payload()["csv"].replace("5.00000000", "2.50000000").replace('"2.416,10 $"', '"--"')
    text = text.replace('"B/P diario","19,71 / 0,12% €"', '"B/P diario","-2,15 / -0,01% €"')
    text = text.replace('"482,43","483,22"', '"--","483,22"')
    variant = valuation(client, confirm(client, payload(text)))
    msft = variant["imported"]["export"]["rows"][1]
    assert msft["quantity"] == "2.50000000" and msft["economics"]["average_price"] is None
    assert msft["economics"]["market_value"] is None
    assert Decimal(variant["valuation"]["positions"][1]["quote_value"]) == Decimal("1208.05")
    assert variant["imported"]["export"]["totals"]["daily_pnl"] == {
        "money": {"amount": "-2.15", "currency": "EUR"}, "percentage": "-0.01",
    }
    assert variant["imported"]["export"]["totals"]["open_pnl"] == totals["open_pnl"]
    assert counts(path) == (0, 0, 2)


def test_a3_a4_lots_rejections_and_idempotency(demo):
    client, path = demo
    native = payload()["csv"]
    header = native.splitlines()[1]
    document = payload("\ufeff" + native.replace(header, header + "\n" + header, 1))
    token = preview(client, document)["preview_token"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(client, document, token), range(2)))
    saved = results[0]
    assert results == [saved, saved] and confirm(client, document) == saved
    assert counts(path) == (0, 0, 1)
    original = valuation(client, saved)

    msft_lot = '"","Microsoft","MSFT.O","NASDAQ","25/11/2026","Compra","5.00000000","482,43"'
    first_lot = msft_lot.replace("5.00000000", "2.00000000")
    second_lot = msft_lot.replace("5.00000000", "3.00000000").replace("25/11/2026", "24/11/2026")
    modified = document["csv"].replace(msft_lot, first_lot + "\n" + second_lot)
    previewed = preview(client, payload(modified))
    assert len(previewed["rows"][1]["lots"]) == 2
    assert valuation(client, saved) == original  # Revisar y cancelar equivale a no confirmar.
    bad_inputs = ("Symbol,Name,Price\nMSFT,Microsoft,483.22", modified.replace(second_lot, second_lot[:-9]))
    for invalid in bad_inputs:
        rejected = client.post(f"{PREFIX}/investing/preview", json=payload(invalid))
        assert rejected.status_code == 422 and rejected.json()["detail"]
    invalid = preview(client, payload(modified.replace('"5.00000000"', '"no numérica"', 1)))
    assert invalid["preview_token"] is None and "Cantidad" in invalid["rows"][1]["issue"]
    assert valuation(client, saved) == original

    repriced = modified.replace('"483,22","2.416,10 $"', '"500,00","2.500,00 $"')
    second = confirm(client, payload(repriced))
    revised = valuation(client, second)
    assert second["portfolio_version"] == 2 and second["valuation_id"] != saved["valuation_id"]
    assert len(revised["imported"]["export"]["rows"][1]["lots"]) == 2
    assert revised["imported"]["export"]["rows"][1]["quantity"] == "5.00000000"
    without_nvda = "\n".join(line for line in repriced.splitlines() if '"NVDA.O"' not in line)
    third = confirm(client, payload(without_nvda))
    assert third["portfolio_version"] == 3 and len(valuation(client, third)["portfolio"]["positions"]) == 2
    store = ValuationSnapshotStore(path)
    assert len(store.portfolio_version(saved["portfolio_id"], 1).positions) == 3
    assert store.get(saved["valuation_id"]) is not None
    assert client.post(f"{PREFIX}/investing/confirm", json={**document, "preview_token": token}).status_code == 409


def test_a5_a6_worker_uses_frozen_version_and_preserves_history(demo, monkeypatch):
    client, path = demo
    file = str(path)
    saved = confirm(client, payload())
    legacy = client.post("/api/analyses").json()
    assert db.process_one(file) == legacy["id"]
    legacy_report = client.get(f'/api/analyses/{legacy["id"]}').json()["report_id"]
    legacy_before = client.get(f"/api/reports/{legacy_report}").json()
    queued = queue(client, saved)
    newer = confirm(client, payload(payload()["csv"].replace("5.00000000", "2.50000000")))
    assert newer["portfolio_version"] == 2
    other = confirm(client, payload(account="Otra cuenta"))
    assert other["portfolio_id"] != saved["portfolio_id"]
    profile = client.get("/api/profile").json()["data"]
    client.put("/api/profile", json={**profile, "name": "Cambio posterior"})
    assert db.process_one(file) == queued["id"]
    completed = client.get(f'/api/analyses/{queued["id"]}').json()
    assert completed["status"] == "completed"
    report = client.get(f'/api/reports/{completed["report_id"]}').json()
    context = PortfolioTestInput.model_validate(report["input_snapshot"]["portfolio_analysis"])
    result = PortfolioTestResult.model_validate(report["result"])
    assert context.view.valuation.snapshot_id == saved["valuation_id"] == result.selection.valuation_id
    assert context.profile.name == profile["name"] and len(context.documents) == 1
    assert result.selection.portfolio_version == 1 and result.selection.portfolio_id == saved["portfolio_id"]
    msft = next(row for row in result.direct_positions if row.ticker == "MSFT")
    assert msft.quantity == Decimal("5") and msft.weight_pct == Decimal("13.48")
    assert result.declared_total.amount == Decimal("16320.14")
    assert result.open_pnl.money.amount == Decimal("19.71")
    assert result.funds_without_holdings == ("SPY",)
    assert counts(path) == (2, 2, 3)
    assert client.get(f"/api/reports/{legacy_report}").json() == legacy_before

    def fail(_):
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(db, "analyze_portfolio_snapshot", fail)
    failed = queue(client, newer)
    assert db.process_one(file) == failed["id"]
    run = client.get(f'/api/analyses/{failed["id"]}').json()
    assert run["status"] == "failed" and run["report_id"] is None
    assert valuation(client, newer)["valuation"]["snapshot_id"] == newer["valuation_id"]
    assert client.post("/api/analyses", json={
        "portfolio_id": saved["portfolio_id"], "portfolio_version": 1, "valuation_id": newer["valuation_id"],
    }).status_code == 404


def test_a7_only_refresh_uses_prices_and_preserves_original(demo, monkeypatch):
    client, path = demo
    saved = confirm(client, payload())
    calls = []
    now = ACCEPTANCE_AT

    class Prices:
        fail = True

        def __init__(self, token):
            assert token == "demo-placeholder"

        def get_latest(self, *, start, end, symbol, **fields):
            calls.append(symbol)
            if self.fail:
                raise OSError("fallo controlado")
            return MarketObservation(observation_id=symbol, **fields, value="100", price_as_of=end,
                                     provider="EODHD", source="Prueba", license="fixture", retrieved_at=now,
                                     is_simulated=True)

    class Rates:
        def get_rate(self, base, quote, day):
            calls.append("BCE")
            return FXObservation(observation_id="fx", base_currency=base, quote_currency=quote, as_of=day,
                                 rate="1.2", provider="BCE", source="Prueba", license="fixture",
                                 retrieved_at=now, is_simulated=True)

    monkeypatch.setattr(refresh, "EODHDPriceProvider", Prices)
    monkeypatch.setattr(refresh, "ECBFXProvider", Rates)
    params = {"portfolio_id": saved["portfolio_id"]}
    assert client.post(f"{PREFIX}/refresh-prices", params=params).status_code == 502
    assert valuation(client, saved)["valuation"]["snapshot_id"] == saved["valuation_id"]
    assert calls == ["SPY.US", "MSFT.US", "NVDA.US"]
    Prices.fail = False
    updated = client.post(f"{PREFIX}/refresh-prices", params=params)
    assert updated.status_code == 201, updated.text
    after = updated.json()
    assert after["valuation_mode"] == "live" and after["valuation"]["snapshot_id"] != saved["valuation_id"]
    assert after["valuation"]["portfolio_version"] == 1 and after["valuation"]["valued_positions"] == 3
    assert after["valuation"]["price_observations"][0]["provider"] == "EODHD"
    assert after["imported"]["valuation_id"] == saved["valuation_id"]
    assert after["imported"]["export"]["totals"]["open_pnl"]["money"]["amount"] == "19.71"
    assert valuation(client, saved, view="imported")["valuation"]["snapshot_id"] == saved["valuation_id"]
    assert calls[3:] == ["SPY.US", "MSFT.US", "NVDA.US", "BCE"]
    assert counts(path) == (0, 0, 1)
    run = queue(client, {**saved, "valuation_id": after["valuation"]["snapshot_id"]})
    assert db.process_one(str(path)) == run["id"]
    report_id = client.get(f'/api/analyses/{run["id"]}').json()["report_id"]
    result = client.get(f"/api/reports/{report_id}").json()["result"]
    assert result["selection"]["valuation_id"] == after["valuation"]["snapshot_id"]
    assert result["declared_valuation_id"] == saved["valuation_id"]
    assert next(row for row in result["direct_positions"] if row["ticker"] == "MSFT")["weight_source"] == "calculated"


def test_portable_input_and_output_from_demo():
    sample = Path(__file__).resolve().parents[1] / "docs/ejemplos/analisis_cartera_importada_demo.json"
    example = json.loads(sample.read_text(encoding="utf-8"))
    context = PortfolioTestInput.model_validate(example["input"])
    assert analyze_portfolio_snapshot(context) == PortfolioTestResult.model_validate(example["output"])
