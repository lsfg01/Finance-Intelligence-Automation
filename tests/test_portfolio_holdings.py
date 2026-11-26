from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.main import create_app
from app.portfolio import alpaca
from app.portfolio.valuation_store import ValuationSnapshotStore


PREFIX = "/api/portfolio"
CSV = "\ufeffSímbolo;Nombre;Bolsa;Cantidad;Fecha de referencia\r\nMSFT;Microsoft Corp;NASDAQ;2,5;2024-01-16\r\n"
PAPER_ACCOUNT = "38f2ba2c-f19f-4068-a2fc-73d9b1a15ef4"
MSFT = {
    "asset_id": "c921e759-2062-40e9-a2f6-b7e0ecd122dd",
    "asset_class": "us_equity",
    "symbol": "MSFT",
    "exchange": "NASDAQ",
    "qty": "2.5",
    "side": "long",
    "current_price": "1",  # Valuation must use the I1 price.
}


def test_investing_export_reads_one_positions_section(tmp_path):
    csv = """\ufeff"Resumen de posiciones"
"","Nombre","Símbolo","Mercado","Tipo","Cantidad"
"","SPDR S&P 500","SPY","NYSE","Compra","20.00000000"
"","Microsoft","MSFT.O","NASDAQ","Compra","2.50000000"
"","NVIDIA","NVDA.O","NASDAQ","Compra","10.00000000"

"Val. mercado","100,00 €"
"B/P total","19,71 €"

"Posiciones abiertas"
"","Nombre","Símbolo","Mercado","Fecha apertura","Tipo","Cantidad"
"","SPDR S&P 500","SPY","NYSE","25/11/2026","Compra","20.00000000"
"","Microsoft","MSFT.O","NASDAQ","25/11/2026","Compra","2.50000000"
"","NVIDIA","NVDA.O","NASDAQ","25/11/2026","Compra","10.00000000"
"""
    payload = {"account": "Demo Holdings", "csv": csv}
    expected = {"E04-ARCX": Decimal("20"), "A02-XNAS": Decimal("2.5"), "A03-XNAS": Decimal("10")}
    with TestClient(create_app(str(tmp_path / "native-shape.sqlite3"))) as client:
        for _ in range(2):
            preview = client.post(f"{PREFIX}/investing/preview", json=payload).json()
            assert {row["listing_id"]: Decimal(row["quantity"]) for row in preview["rows"]} == expected
            assert len(preview["rows"]) == 3
            confirmed = client.post(f"{PREFIX}/investing/confirm", json={
                **payload, "preview_token": preview["preview_token"],
            })
            assert confirmed.status_code == 201
            result = client.post(f"{PREFIX}/refresh-prices", params={
                "portfolio_id": confirmed.json()["portfolio_id"], "mode": "simulated",
            }).json()
            assert result["source"]["reference_date"] is None
            assert result["portfolio"]["version"] == 1
            assert result["valuation"]["valued_positions"] == 3
            msft = next(row for row in result["valuation"]["positions"] if row["position"]["listing_id"] == "A02-XNAS")
            assert Decimal(msft["position"]["quantity"]) == Decimal("2.5")
            assert Decimal(msft["quote_value"]) == Decimal("728.75")

        short = client.post(f"{PREFIX}/investing/preview", json={
            **payload, "csv": csv.replace('"Compra","2.50000000"', '"Venta","2.50000000"', 1),
        }).json()
        assert short["preview_token"] is None
        assert "Tipo de posición incompatible" in short["rows"][1]["issue"]


def configure_oauth(monkeypatch):
    monkeypatch.setenv("ALPACA_OAUTH_CLIENT_ID", "demo-client")
    monkeypatch.setenv("ALPACA_OAUTH_CLIENT_SECRET", "demo-secret")
    monkeypatch.setenv("ALPACA_OAUTH_REDIRECT_URI", "http://testserver/api/portfolio/alpaca/callback")


def start_oauth(client):
    response = client.get(f"{PREFIX}/alpaca/authorize", follow_redirects=False)
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert (location.scheme, location.netloc, location.path) == ("https", "app.alpaca.markets", "/oauth/authorize")
    query = parse_qs(location.query)
    assert query["env"] == ["paper"]
    assert "scope" not in query
    return query["state"][0]


def test_offline_demo_loads_and_values_msft_separately(tmp_path, monkeypatch):
    configure_oauth(monkeypatch)
    path = tmp_path / "holdings.sqlite3"
    requests = []
    provider_positions = [MSFT]

    def request_json(request):
        requests.append((request.get_method(), request.full_url))
        if request.full_url == alpaca.TOKEN_URL:
            form = parse_qs(request.data.decode("ascii"))
            assert form["code"] == ["offline-code"]
            assert form["client_secret"] == ["demo-secret"]
            return {"access_token": "offline-token", "scope": ""}
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") == "Bearer offline-token"
        if request.full_url == f"{alpaca.PAPER_API}/v2/account":
            return {"id": PAPER_ACCOUNT, "currency": "USD"}
        assert request.full_url == f"{alpaca.PAPER_API}/v2/positions"
        return provider_positions

    monkeypatch.setattr(alpaca, "request_json", request_json)
    with TestClient(create_app(str(path))) as client:
        assert client.post(f"{PREFIX}/alpaca/sync").status_code == 409
        state = start_oauth(client)
        connected = client.get(f"{PREFIX}/alpaca/callback", params={"state": state, "code": "offline-code"},
                               follow_redirects=False)
        assert connected.headers["location"] == "/?paper=connected"
        assert len(client.get(f"{PREFIX}/holdings").json()) == 1

        for version in (1, 2):
            payload = {"account": "Demo MSFT", "csv": CSV}
            preview = client.post(f"{PREFIX}/investing/preview", json=payload).json()
            assert preview["rows"][0]["quantity"] == "2.5"
            assert preview["rows"][0]["listing_id"] == "A02-XNAS"
            assert preview["rows"][0]["issue"] is None
            assert len(client.get(f"{PREFIX}/holdings").json()) == (1 if version == 1 else 3)
            confirm = {**payload, "preview_token": preview["preview_token"]}
            assert client.post(f"{PREFIX}/investing/confirm", json={
                **confirm, "csv": CSV.replace("2,5", "3,5"),
            }).status_code == 409
            imported = client.post(f"{PREFIX}/investing/confirm", json=confirm)
            synced = client.post(f"{PREFIX}/alpaca/sync")
            assert imported.status_code == synced.status_code == 201
            invested_id = imported.json()["portfolio_id"]
            paper_id = synced.json()["portfolio_id"]
            assert paper_id == f"alpaca-paper:{PAPER_ACCOUNT}" and paper_id != invested_id
            assert len(client.get(f"{PREFIX}/holdings").json()) == 3
            assert client.post(f"{PREFIX}/investing/confirm", json=confirm).json() == imported.json()

            for portfolio_id, provider, reference, currency in (
                (invested_id, "investing.com", "2024-01-16", "EUR"),
                (paper_id, "alpaca-paper", None, "USD"),
            ):
                params = {"portfolio_id": portfolio_id}
                before = client.get(f"{PREFIX}/valuation", params=params).json()
                if provider == "investing.com":
                    assert before["valuation"] is not None
                    assert before["portfolio"]["version"] == 1
                else:
                    assert before["valuation"] is None
                    assert before["portfolio"]["version"] == version
                assert before["portfolio"]["accounts"][0]["account_id"] == portfolio_id
                assert before["source"]["provider"] == provider
                assert before["source"]["reference_date"] == reference
                assert before["source"]["loaded_at"].endswith("Z")
                assert before["portfolio"]["as_of"] == (reference or before["source"]["loaded_at"][:10])
                assert len(before["portfolio"]["positions"]) == 1
                position = before["portfolio"]["positions"][0]
                assert (position["instrument_id"], position["listing_id"], position["quantity"]) == (
                    "A02", "A02-XNAS", "2.5",
                )
                refresh = client.post(f"{PREFIX}/refresh-prices", params={**params, "mode": "simulated"})
                assert refresh.status_code == 201
                result = refresh.json()
                valuation = result["valuation"]
                assert result["source"] == before["source"]
                assert valuation["status"] == "COMPLETE"
                assert valuation["base_currency"] == currency
                assert Decimal(valuation["positions"][0]["quote_value"]) == Decimal("728.75")
                assert Decimal(valuation["total_value"]).quantize(Decimal("0.01")) == (
                    Decimal("647.78") if currency == "EUR" else Decimal("728.75")
                )
                assert client.get(f"{PREFIX}/valuation", params=params).json() == result
                if version == 1:
                    if portfolio_id == invested_id:
                        first_investing_valuation = valuation["snapshot_id"]
                    else:
                        first_paper_valuation = valuation["snapshot_id"]

        ambiguous = client.post(f"{PREFIX}/investing/preview", json={
            "account": "Demo MSFT", "csv": CSV + "MSFT;Microsoft;;1,25;2024-01-16\r\n",
        }).json()
        assert ambiguous["preview_token"] is None
        assert ambiguous["rows"][1]["quantity"] == "1.25"
        assert "Plaza ambigua" in ambiguous["rows"][1]["issue"]
        provider_positions.append({**MSFT, "qty": "inválida"})
        assert client.post(f"{PREFIX}/alpaca/sync").status_code == 502
        assert client.get("/api/reports").json() == []

    with TestClient(create_app(str(path))) as restarted:
        for portfolio_id in (invested_id, paper_id):
            current = restarted.get(f"{PREFIX}/valuation", params={"portfolio_id": portfolio_id}).json()
            assert current["portfolio"]["version"] == (1 if portfolio_id == invested_id else 2)
            assert current["valuation"]["status"] == "COMPLETE"
        assert restarted.post(f"{PREFIX}/alpaca/sync").status_code == 409
    store = ValuationSnapshotStore(path)
    for snapshot_id in (first_investing_valuation, first_paper_valuation):
        assert store.get(snapshot_id).portfolio_version == 1
    assert requests.count(("GET", f"{alpaca.PAPER_API}/v2/positions")) == 3


def test_alpaca_rejects_invalid_state_and_write_scope(tmp_path, monkeypatch):
    configure_oauth(monkeypatch)
    calls = []

    def request_json(request):
        calls.append(request.full_url)
        return {"access_token": "offline-token", "scope": "account:write trading"}

    monkeypatch.setattr(alpaca, "request_json", request_json)
    with TestClient(create_app(str(tmp_path / "oauth.sqlite3"))) as client:
        for matches in (False, True):
            state = start_oauth(client)
            response = client.get(f"{PREFIX}/alpaca/callback", params={
                "state": state if matches else "wrong-state", "code": "offline-code",
            }, follow_redirects=False)
            assert response.headers["location"] == "/?paper=error"
            assert client.post(f"{PREFIX}/alpaca/sync").status_code == 409
            assert calls == ([alpaca.TOKEN_URL] if matches else [])
