from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status

from .fixtures import DEMO_INSTRUMENTS, DEMO_LISTINGS, DEMO_PORTFOLIO
from .models import DomainModel, Instrument, Listing, PortfolioSnapshot
from .refresh import MarketCredentialsRejected, refresh_demo_prices, refresh_market_prices
from .valuation import ValuationSnapshot
from .valuation_store import PriceMode, ValuationSnapshotStore


class PortfolioValuationResponse(DomainModel):
    portfolio: PortfolioSnapshot
    valuation: ValuationSnapshot | None
    valuation_mode: PriceMode | None
    instruments: tuple[Instrument, ...] = DEMO_INSTRUMENTS
    listings: tuple[Listing, ...] = DEMO_LISTINGS


def valuation_router(database_path: Path) -> APIRouter:
    store: ValuationSnapshotStore

    @asynccontextmanager
    async def lifespan(_):
        nonlocal store
        store = ValuationSnapshotStore(database_path)
        store.save_portfolio(DEMO_PORTFOLIO)
        yield

    router = APIRouter(prefix="/api/portfolio", lifespan=lifespan)

    def active_portfolio() -> PortfolioSnapshot:
        portfolio = store.latest_portfolio(DEMO_PORTFOLIO.portfolio_id)
        if portfolio is None:
            raise RuntimeError("No está inicializada la cartera multiactivo")
        return portfolio

    @router.get("/valuation")
    def get_valuation() -> PortfolioValuationResponse:
        portfolio = active_portfolio()
        valuation, mode = store.latest_for_portfolio(portfolio)
        if valuation is not None and mode is None:
            observations = valuation.price_observations
            # En los snapshots anteriores, solo el refresco de mercado usaba una ventana de varios días.
            is_market = any(not price.is_simulated for price in observations)
            if not observations:
                is_market = valuation.max_price_age_days > 0
            mode = "live" if is_market else "simulated"
        return PortfolioValuationResponse(portfolio=portfolio, valuation=valuation, valuation_mode=mode)

    @router.post("/refresh-prices", status_code=status.HTTP_201_CREATED)
    def refresh_prices(mode: Literal["auto", "simulated", "live"] = "auto") -> PortfolioValuationResponse:
        portfolio = active_portfolio()
        market_enabled = os.environ.get("ENABLE_LIVE_MARKET_DATA") == "1"
        if mode == "auto":
            mode = "live" if market_enabled else "simulated"
        if mode == "live":
            token = os.environ.get("EODHD_API_TOKEN", "").strip()
            if not market_enabled:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sin proveedor autorizado de precios reales")
            if not token:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Falta configurar EODHD_API_TOKEN")
            try:
                valuation = refresh_market_prices(store, portfolio, token)
            except MarketCredentialsRejected:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "EODHD rechazó la credencial configurada") from None
        else:
            valuation = refresh_demo_prices(store, portfolio)
        return PortfolioValuationResponse(portfolio=portfolio, valuation=valuation, valuation_mode=mode)

    return router
