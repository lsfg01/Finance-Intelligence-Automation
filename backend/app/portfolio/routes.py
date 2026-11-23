from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status

from .fixtures import DEMO_INSTRUMENTS, DEMO_LISTINGS, DEMO_PORTFOLIO
from .models import DomainModel, Instrument, Listing, PortfolioSnapshot
from .refresh import refresh_demo_prices
from .valuation import ValuationSnapshot
from .valuation_store import ValuationSnapshotStore


class PortfolioValuationResponse(DomainModel):
    portfolio: PortfolioSnapshot
    valuation: ValuationSnapshot | None
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
        return PortfolioValuationResponse(portfolio=portfolio, valuation=store.latest_for_portfolio(portfolio))

    @router.post("/refresh-prices", status_code=status.HTTP_201_CREATED)
    def refresh_prices(mode: Literal["simulated", "live"] = "simulated") -> PortfolioValuationResponse:
        if mode == "live":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sin proveedor autorizado de precios reales")
        portfolio = active_portfolio()
        return PortfolioValuationResponse(portfolio=portfolio, valuation=refresh_demo_prices(store, portfolio))

    return router
