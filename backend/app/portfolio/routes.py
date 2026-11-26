from contextlib import asynccontextmanager
from csv import Error as CSVError
from datetime import date, datetime, timezone
from hashlib import sha256
import hmac
import os
from pathlib import Path
from secrets import token_urlsafe
from time import monotonic
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from . import alpaca
from .fixtures import DEMO_INSTRUMENTS, DEMO_LISTINGS, DEMO_PORTFOLIO
from .holdings import ConfirmImport, HoldingsSource, ImportFile, InvestingExport, build_holdings, normalize, read_investing
from .import_valuation import ImportedValuation
from .models import Account, DomainModel, Instrument, Listing, PortfolioSnapshot
from .refresh import MarketCredentialsRejected, MarketPricesUnavailable, refresh_demo_prices, refresh_market_prices
from .valuation import ValuationSnapshot
from .valuation_store import PortfolioVersionChanged, PriceMode, ValuationSnapshotStore


class PortfolioValuationResponse(DomainModel):
    portfolio: PortfolioSnapshot
    valuation: ValuationSnapshot | None
    valuation_mode: PriceMode | None
    source: HoldingsSource | None = None
    imported: ImportedValuation | None = None
    instruments: tuple[Instrument, ...] = DEMO_INSTRUMENTS
    listings: tuple[Listing, ...] = DEMO_LISTINGS


class PortfolioChoice(DomainModel):
    portfolio_id: str
    name: str


class ImportPreview(InvestingExport):
    preview_token: str | None


class ImportConfirmation(PortfolioChoice):
    portfolio_version: int
    valuation_id: str


def valuation_router(database_path: Path) -> APIRouter:
    store: ValuationSnapshotStore
    preview_key = os.urandom(32)
    paper_token: str | None = None
    oauth_attempt: tuple[str, float] | None = None

    @asynccontextmanager
    async def lifespan(_):
        nonlocal store, paper_token, oauth_attempt
        store = ValuationSnapshotStore(database_path)
        store.save_portfolio(DEMO_PORTFOLIO)
        yield
        paper_token = oauth_attempt = None

    router = APIRouter(prefix="/api/portfolio", lifespan=lifespan)

    def selected_portfolio(portfolio_id: str) -> PortfolioSnapshot:
        portfolio = store.latest_portfolio(portfolio_id)
        if portfolio is None:
            raise HTTPException(404, "Cartera multiactivo no encontrada")
        return portfolio

    def current_version(portfolio_id: str) -> int:
        portfolio = store.latest_portfolio(portfolio_id)
        return portfolio.version if portfolio else 0

    def saving_load(portfolio: PortfolioSnapshot, source: HoldingsSource, version: int) -> PortfolioChoice:
        try:
            saved = store.save_loaded_portfolio(portfolio, source, expected_version=version)
        except PortfolioVersionChanged:
            raise HTTPException(409, "La cartera cambió durante la carga. Repite la operación") from None
        return PortfolioChoice(portfolio_id=saved.portfolio_id, name=saved.accounts[0].name)

    @router.get("/holdings")
    def list_holdings() -> tuple[PortfolioChoice, ...]:
        return tuple(
            PortfolioChoice(
                portfolio_id=portfolio.portfolio_id,
                name="Demo multiactivo I1" if portfolio.portfolio_id == DEMO_PORTFOLIO.portfolio_id
                else portfolio.accounts[0].name,
            )
            for portfolio in store.list_portfolios()
        )

    def investing_account(name: str) -> Account:
        identity = sha256(normalize(name).encode("utf-8")).hexdigest()
        return Account(account_id=f"investing:{identity}", name=f"Investing.com · {name}")

    def import_signature(payload: ImportFile, version: int) -> str:
        document = payload.model_dump_json(include={"account", "csv", "filename"})
        signature = hmac.new(preview_key, f"{version}:{document}".encode("utf-8"), "sha256").hexdigest()
        return f"{version}:{signature}"

    def investing_export(payload: ImportFile, today: date) -> InvestingExport:
        try:
            export = read_investing(payload.csv, payload.filename or "")
        except CSVError:
            raise HTTPException(422, "El CSV no está bien formado") from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if export.reference_date and export.reference_date > today:
            raise HTTPException(422, "La fecha de referencia es posterior a la carga")
        return export

    @router.post("/investing/preview")
    def preview_investing(payload: ImportFile) -> ImportPreview:
        account = investing_account(payload.account)
        export = investing_export(payload, datetime.now(timezone.utc).date())
        token = None if any(row.issue for row in export.rows) else import_signature(payload, current_version(account.account_id))
        return ImportPreview(**export.model_dump(), preview_token=token)

    @router.post("/investing/confirm", status_code=201)
    def confirm_investing(payload: ConfirmImport) -> ImportConfirmation:
        account = investing_account(payload.account)
        version = int(payload.preview_token.partition(":")[0])
        if not hmac.compare_digest(import_signature(payload, version), payload.preview_token):
            raise HTTPException(409, "La vista previa cambió o caducó. Genera una nueva")
        now = datetime.now(timezone.utc)
        export = investing_export(payload, now.date())
        if any(row.issue for row in export.rows):
            raise HTTPException(422, "La importación contiene posiciones sin resolver")
        portfolio, source = build_holdings(account, export.rows, "investing.com", now)
        source = source.model_copy(update={"reference_origin": export.reference_origin})
        canonical_csv = payload.csv.removeprefix("\ufeff").replace("\r\n", "\n")
        digest = sha256(f"{export.reference_date}:{canonical_csv}".encode("utf-8")).hexdigest()
        try:
            saved = store.save_loaded_portfolio(portfolio, source, expected_version=version,
                                                export=export, digest=digest)
        except PortfolioVersionChanged:
            raise HTTPException(409, "La cartera cambió desde la vista previa. Genera una nueva") from None
        imported = store.get_import(saved.snapshot_id)
        assert imported is not None
        return ImportConfirmation(portfolio_id=saved.portfolio_id, name=saved.accounts[0].name,
                                  portfolio_version=saved.version, valuation_id=imported.valuation_id)

    def oauth_settings() -> tuple[str, str, str]:
        client_id = os.environ.get("ALPACA_OAUTH_CLIENT_ID", "").strip()
        secret = os.environ.get("ALPACA_OAUTH_CLIENT_SECRET", "").strip()
        redirect_uri = os.environ.get("ALPACA_OAUTH_REDIRECT_URI", "").strip()
        if not (client_id and secret and redirect_uri):
            raise HTTPException(503, "Falta configurar el cliente OAuth de Alpaca Paper")
        return client_id, secret, redirect_uri

    @router.get("/alpaca/authorize")
    async def authorize_paper() -> RedirectResponse:
        nonlocal oauth_attempt
        try:
            client_id, _, redirect_uri = oauth_settings()
        except HTTPException:
            return RedirectResponse("/?paper=unconfigured", status_code=303)
        state = token_urlsafe(32)
        oauth_attempt = (state, monotonic() + 300)
        query = urlencode({
            "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
            "state": state, "env": "paper",
        })
        response = RedirectResponse(f"{alpaca.AUTHORIZE_URL}?{query}", status_code=303)
        response.set_cookie("alpaca_oauth_state", state, max_age=300, httponly=True,
                            secure=redirect_uri.startswith("https://"), path="/api/portfolio/alpaca/callback")
        return response

    @router.get("/alpaca/callback")
    async def connect_paper(request: Request, code: str = "", state: str = "") -> RedirectResponse:
        nonlocal oauth_attempt, paper_token
        # Uvicorn reads the ASGI scope when logging the response.
        request.scope["query_string"] = b""
        outcome = "error"
        if (oauth_attempt and oauth_attempt[1] >= monotonic() and state.isascii()
                and hmac.compare_digest(state, oauth_attempt[0])
                and state == request.cookies.get("alpaca_oauth_state")):
            oauth_attempt = None
            if code:
                try:
                    paper_token = await run_in_threadpool(alpaca.exchange_code, code, *oauth_settings())
                    outcome = "connected"
                except (alpaca.AlpacaError, HTTPException):
                    pass
        response = RedirectResponse(f"/?paper={outcome}", status_code=303,
                                    headers={"Referrer-Policy": "no-referrer"})
        response.delete_cookie("alpaca_oauth_state", path="/api/portfolio/alpaca/callback")
        return response

    @router.post("/alpaca/sync", status_code=201)
    def sync_paper() -> PortfolioChoice:
        token = paper_token
        if not token:
            raise HTTPException(409, "Conecta primero una cuenta Alpaca Paper")
        try:
            account, currency = alpaca.read_account(token)
            version = current_version(account.account_id)
            rows = alpaca.read_positions(token)
        except alpaca.AlpacaError as error:
            raise HTTPException(502, str(error)) from None
        portfolio, source = build_holdings(account, rows, "alpaca-paper", datetime.now(timezone.utc),
                                           base_currency=currency)
        return saving_load(portfolio, source, version)

    @router.get("/valuation")
    def get_valuation(
        portfolio_id: str = DEMO_PORTFOLIO.portfolio_id, view: Literal["latest", "imported"] = "latest",
    ) -> PortfolioValuationResponse:
        portfolio = selected_portfolio(portfolio_id)
        imported = store.get_import(portfolio.snapshot_id)
        if view == "imported" and imported:
            valuation, mode = store.get(imported.valuation_id), "imported"
        else:
            valuation, mode = store.latest_for_portfolio(portfolio)
        if valuation is not None and mode is None:
            observations = valuation.price_observations
            # En los snapshots anteriores, solo el refresco de mercado usaba una ventana de varios días.
            is_market = any(not price.is_simulated for price in observations)
            if not observations:
                is_market = valuation.max_price_age_days > 0
            mode = "live" if is_market else "simulated"
        return PortfolioValuationResponse(portfolio=portfolio, valuation=valuation, valuation_mode=mode,
                                          source=store.get_source(portfolio.snapshot_id), imported=imported)

    @router.post("/refresh-prices", status_code=status.HTTP_201_CREATED)
    def refresh_prices(
        mode: Literal["auto", "simulated", "live"] = "auto", portfolio_id: str = DEMO_PORTFOLIO.portfolio_id,
    ) -> PortfolioValuationResponse:
        portfolio = selected_portfolio(portfolio_id)
        imported = store.get_import(portfolio.snapshot_id)
        market_enabled = os.environ.get("ENABLE_LIVE_MARKET_DATA") == "1"
        if mode == "auto":
            mode = "live" if market_enabled or imported else "simulated"
        if mode == "live":
            token = os.environ.get("EODHD_API_TOKEN", "").strip()
            if not market_enabled:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sin proveedor autorizado de precios reales")
            if not token:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Falta configurar EODHD_API_TOKEN")
            try:
                valuation = refresh_market_prices(store, portfolio, token, require_prices=imported is not None)
            except MarketCredentialsRejected:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "EODHD rechazó la credencial configurada") from None
            except MarketPricesUnavailable:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "El proveedor no devolvió precios utilizables") from None
        else:
            valuation = refresh_demo_prices(store, portfolio)
        return PortfolioValuationResponse(portfolio=portfolio, valuation=valuation, valuation_mode=mode,
                                          source=store.get_source(portfolio.snapshot_id), imported=imported)

    return router
