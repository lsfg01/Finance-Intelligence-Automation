import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market_data import ecb, eodhd
from app.portfolio import refresh
from app.portfolio.fixtures import DEMO_PORTFOLIO
from app.portfolio.valuation_store import ValuationSnapshotStore


@pytest.mark.parametrize("same_day_fx", [True, False])
def test_live_refresh_uses_exact_nav_listings_and_dated_fx(tmp_path, monkeypatch, same_day_fx):
    path = tmp_path / "market.sqlite3"

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz):
            return cls(2026, 11, 23, 12, tzinfo=tz)

    monkeypatch.setattr(ecb, "datetime", FixedDatetime)
    monkeypatch.setattr(eodhd, "datetime", FixedDatetime)
    monkeypatch.setattr(refresh, "datetime", FixedDatetime)
    today = FixedDatetime.now(timezone.utc).date()
    nav_day = today - timedelta(days=2)
    close_day = today - timedelta(days=1)
    calls = []
    # Importes inventados, incluidos cierres ajustados distintos para detectar su uso accidental.
    closes = {
        "IE00B03HD191.EUFUND": (nav_day, "60.1234"),
        "IE00BYX5NX33.EUFUND": (nav_day, "13.4321"),
        "IE00B18GC888.EUFUND": (nav_day, "98.5678"),
        "EUNL.XETRA": (close_day, "122.10"),
        "MSFT.US": (close_day, "440.00"),
        "IBE.MC": (today - timedelta(days=8), "20.50"),
    }

    def market_response(request, timeout):
        url = urlsplit(request.full_url)
        assert url.hostname == "eodhd.com"
        query = parse_qs(url.query)
        assert query["api_token"] == ["fixture-token"]
        assert query["period"] == ["d"]
        assert query["from"] == [(today - timedelta(days=7)).isoformat()]
        assert query["to"] == [today.isoformat()]
        symbol = url.path.rsplit("/", 1)[-1]
        calls.append(symbol)
        if symbol == "ES0156572002.EUFUND":
            raise HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO())
        if symbol == "EUNA.XETRA":
            return io.BytesIO(b'{"message":"unexpected payload"}')
        if symbol not in closes:
            return io.BytesIO(b"[]")
        day, close = closes[symbol]
        return io.BytesIO(
            f'[{{"date":"{day}","close":{close},"adjusted_close":1.01}}]'.encode()
        )

    def fx_response(request, timeout):
        url = urlsplit(request.full_url)
        assert url.hostname == "data-api.ecb.europa.eu"
        assert parse_qs(url.query)["endPeriod"] == [close_day.isoformat()]
        calls.append(ecb.SERIES_ID)
        date = close_day if same_day_fx else nav_day
        return io.BytesIO(f"KEY,TIME_PERIOD,OBS_VALUE\n{ecb.SERIES_ID},{date},1.1000\n".encode())

    monkeypatch.setenv("ENABLE_LIVE_MARKET_DATA", "1")
    monkeypatch.setenv("EODHD_API_TOKEN", "fixture-token")
    monkeypatch.setattr(eodhd, "urlopen", market_response)
    monkeypatch.setattr(ecb, "urlopen", fx_response)

    with TestClient(create_app(str(path))) as client:
        initial = client.get("/api/portfolio/valuation").json()
        assert initial["valuation"] is None
        assert calls == []
        response = client.post("/api/portfolio/refresh-prices?mode=live")
        assert response.status_code == 201
        assert "fixture-token" not in response.text
        market = response.json()
        assert market["portfolio"] == initial["portfolio"]
        valuation = market["valuation"]
        assert valuation["portfolio_snapshot_id"] == market["portfolio"]["snapshot_id"]
        assert valuation["portfolio_version"] == market["portfolio"]["version"]
        assert valuation["total_value"] is None
        assert valuation["valued_positions"] == (5 if same_day_fx else 4)
        assert valuation["total_positions"] == 11
        assert Decimal(valuation["known_value"]) == Decimal("4208.9626625" if same_day_fx else "2608.9626625")
        assert valuation["is_simulated"]  # Las tenencias son ficticias.
        prices = {item["instrument_id"]: item for item in valuation["price_observations"]}
        nav_symbols = {
            "F01": "IE00B03HD191.EUFUND",
            "F02": "IE00BYX5NX33.EUFUND",
            "F03": "IE00B18GC888.EUFUND",
        }
        for instrument_id, symbol in nav_symbols.items():
            price = prices[instrument_id]
            assert price["price_type"] == "NAV"
            assert price["listing_id"] is None
            assert price["value"] == closes[symbol][1]
            assert price["price_as_of"] == nav_day.isoformat()
            assert price["currency"] == "EUR"
            assert price["source"] == f"https://eodhd.com/api/eod/{symbol}"
        assert prices["E01"]["listing_id"] == "E01-XETR"
        assert prices["E01"]["source"] == "https://eodhd.com/api/eod/EUNL.XETRA"
        assert prices["A02"]["listing_id"] == "A02-XNAS"
        assert prices["A02"]["currency"] == "USD"
        assert prices["A02"]["price_type"] == "EOD_CLOSE"
        assert all(not item["is_simulated"] for item in prices.values())
        rows = {row["position"]["instrument_id"]: row for row in valuation["positions"]}
        assert Decimal(rows["A02"]["quote_value"]) == Decimal("1760")
        if same_day_fx:
            rate, = valuation["fx_observations"]
            assert not rate["is_simulated"]
            assert rate["as_of"] == close_day.isoformat()
            assert rows["A02"]["fx_observation_id"] == rate["observation_id"]
            assert Decimal(rows["A02"]["base_value"]) == Decimal("1600")
        else:
            assert valuation["fx_observations"] == []
            assert rows["A02"]["issue"] == "MISSING_FX"
        for instrument_id in ("F04", "E02", "E03", "C01", "K01", "A01"):
            assert rows[instrument_id]["issue"] == "MISSING_PRICE"
            assert rows[instrument_id]["base_value"] is None
        assert "IWDA.LSE" not in calls
        assert calls.count(ecb.SERIES_ID) == 1
        assert client.get("/api/reports").json() == []

    calls.clear()
    with TestClient(create_app(str(path))) as client:
        assert client.get("/api/portfolio/valuation").json() == market
        assert calls == []
        simulated = client.post("/api/portfolio/refresh-prices").json()
        assert simulated["portfolio"] == market["portfolio"]
        assert simulated["valuation"]["valued_positions"] == 10
        assert all(item["is_simulated"] for item in simulated["valuation"]["price_observations"])
        assert calls == []


def test_live_refresh_keeps_an_ambiguous_position_without_looking_up_either_listing(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_MARKET_DATA", "1")
    monkeypatch.setenv("EODHD_API_TOKEN", "fixture-token")
    path = tmp_path / "ambiguous.sqlite3"
    position = next(item for item in DEMO_PORTFOLIO.positions if item.instrument_id == "E01")
    updated = DEMO_PORTFOLIO.model_copy(update={
        "snapshot_id": "SIM-SNAPSHOT-2",
        "version": 2,
        "positions": (position.model_copy(update={"listing_id": None}),),
    })
    ValuationSnapshotStore(path).save_portfolio(updated)

    def unexpected_market_call(*args, **kwargs):
        pytest.fail("An ambiguous position must never query the market")

    monkeypatch.setattr(eodhd, "urlopen", unexpected_market_call)
    monkeypatch.setattr(ecb, "urlopen", unexpected_market_call)
    with TestClient(create_app(str(path))) as client:
        response = client.post("/api/portfolio/refresh-prices?mode=live")
        assert response.status_code == 201
        valuation = response.json()["valuation"]
        assert valuation["portfolio_version"] == 2
        assert valuation["positions"][0]["issue"] == "AMBIGUOUS_LISTING"
        assert valuation["price_observations"] == []
