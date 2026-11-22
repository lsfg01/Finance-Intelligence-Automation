from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status

from .fixtures import DEMO_INSTRUMENTS, DEMO_LISTINGS, DEMO_PORTFOLIO
from .models import DomainModel, Instrument, Listing
from .refresh import refresh_demo_prices
from .valuation import ValuationSnapshot
from .valuation_store import ValuationSnapshotStore


class PortfolioValuationResponse(DomainModel):
    valuation: ValuationSnapshot | None
    instruments: tuple[Instrument, ...] = DEMO_INSTRUMENTS
    listings: tuple[Listing, ...] = DEMO_LISTINGS


def valuation_router(database_path: Path) -> APIRouter:
    store: ValuationSnapshotStore

    @asynccontextmanager
    async def lifespan(_):
        nonlocal store
        store = ValuationSnapshotStore(database_path)
        yield

    router = APIRouter(prefix="/api/portfolio", lifespan=lifespan)

    @router.get("/valuation")
    def get_valuation() -> PortfolioValuationResponse:
        return PortfolioValuationResponse(valuation=store.latest_for_portfolio(DEMO_PORTFOLIO.portfolio_id))

    @router.post("/refresh-prices", status_code=status.HTTP_201_CREATED)
    def refresh_prices(mode: Literal["simulated", "live"] = "simulated") -> PortfolioValuationResponse:
        if mode == "live":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sin proveedor autorizado de precios reales")
        return PortfolioValuationResponse(valuation=refresh_demo_prices(store))

    return router
