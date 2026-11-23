from datetime import datetime, timezone
from uuid import uuid4

from .fixtures import DEMO_AS_OF, DEMO_INSTRUMENTS, DEMO_LISTINGS, FixtureMarketDataProvider
from .models import PortfolioSnapshot
from .valuation import ValuationSnapshot, value_portfolio
from .valuation_store import ValuationSnapshotStore


def refresh_demo_prices(store: ValuationSnapshotStore, portfolio: PortfolioSnapshot) -> ValuationSnapshot:
    """Guarda una valoración de la cartera multiactivo con observaciones simuladas."""
    provider = FixtureMarketDataProvider()
    quotes = tuple(
        observation
        for position in portfolio.positions
        if (observation := provider.get_latest(position.instrument_id, position.listing_id)) is not None
    )
    rate = provider.get_rate(portfolio.base_currency, "USD", DEMO_AS_OF)
    snapshot = value_portfolio(
        portfolio,
        quotes,
        (rate,) if rate is not None else (),
        instruments=DEMO_INSTRUMENTS,
        listings=DEMO_LISTINGS,
        snapshot_id=str(uuid4()),
        as_of=max(DEMO_AS_OF, portfolio.as_of),
        calculated_at=datetime.now(timezone.utc),
    )
    store.save(snapshot)
    return snapshot
