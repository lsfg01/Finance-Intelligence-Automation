from datetime import datetime, timezone
from uuid import uuid4

from .fixtures import DEMO_AS_OF, DEMO_INSTRUMENTS, DEMO_LISTINGS, DEMO_PORTFOLIO, FixtureMarketDataProvider
from .valuation import ValuationSnapshot, value_portfolio
from .valuation_store import ValuationSnapshotStore


def refresh_demo_prices(store: ValuationSnapshotStore) -> ValuationSnapshot:
    """Guarda una valoración de la cartera multiactivo con observaciones simuladas."""
    provider = FixtureMarketDataProvider()
    quotes = tuple(
        observation
        for position in DEMO_PORTFOLIO.positions
        if (observation := provider.get_latest(position.instrument_id, position.listing_id)) is not None
    )
    rate = provider.get_rate(DEMO_PORTFOLIO.base_currency, "USD", DEMO_AS_OF)
    snapshot = value_portfolio(
        DEMO_PORTFOLIO,
        quotes,
        (rate,) if rate is not None else (),
        instruments=DEMO_INSTRUMENTS,
        listings=DEMO_LISTINGS,
        snapshot_id=str(uuid4()),
        as_of=DEMO_AS_OF,
        calculated_at=datetime.now(timezone.utc),
    )
    store.save(snapshot)
    return snapshot
