from csv import Error as CSVError
from datetime import date, datetime, timedelta, timezone
from http.client import HTTPException
from urllib.error import HTTPError
from uuid import uuid4

from app.market_data.ecb import ECBFXProvider
from app.market_data.eodhd import EODHDPriceProvider

from .fixtures import DEMO_AS_OF, DEMO_INSTRUMENTS, DEMO_LISTINGS, FixtureMarketDataProvider
from .models import FXObservation, MarketObservation, PortfolioSnapshot, PriceType
from .valuation import ValuationSnapshot, value_portfolio
from .valuation_store import ValuationSnapshotStore


BITCOIN_EUR_SYMBOL = "BTC-EUR.CC"

# Identidades contrastadas en la matriz del spike y su ampliación.
EODHD_SYMBOLS = {
    ("F01", None): "IE00B03HD191.EUFUND",
    ("F02", None): "IE00BYX5NX33.EUFUND",
    ("F03", None): "IE00B18GC888.EUFUND",
    ("F04", None): "ES0156572002.EUFUND",
    ("E01", "E01-XETR"): "EUNL.XETRA",
    ("E01", "E01-XLON"): "IWDA.LSE",
    ("E02", "E02-XETR"): "VWCE.XETRA",
    ("E03", "E03-XETR"): "EUNA.XETRA",
    ("A01", "A01-XMAD"): "IBE.MC",
    ("A02", "A02-XNAS"): "MSFT.US",
    ("C01", "C01-XETR"): "PPFB.XETRA",
    ("K01", None): BITCOIN_EUR_SYMBOL,
}
LIVE_MAX_PRICE_AGE_DAYS = 7


class MarketCredentialsRejected(Exception):
    """EODHD no acepta la credencial configurada."""


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
    store.save(snapshot, mode="simulated")
    return snapshot


def refresh_market_prices(
    store: ValuationSnapshotStore, portfolio: PortfolioSnapshot, token: str
) -> ValuationSnapshot:
    as_of = datetime.now(timezone.utc).date()
    start = as_of - timedelta(days=LIVE_MAX_PRICE_AGE_DAYS)
    provider = EODHDPriceProvider(token)
    fx_provider = ECBFXProvider()
    instruments = {item.instrument_id: item for item in DEMO_INSTRUMENTS}
    listings = {item.listing_id: item for item in DEMO_LISTINGS}
    quotes: list[MarketObservation] = []
    keys = dict.fromkeys((position.instrument_id, position.listing_id) for position in portfolio.positions)
    for instrument_id, listing_id in keys:
        symbol = EODHD_SYMBOLS.get((instrument_id, listing_id))
        if symbol is None:
            continue
        end = as_of
        if symbol == BITCOIN_EUR_SYMBOL:
            currency = "EUR"
            price_type = PriceType.INDICATIVE
            # EODHD incluye una barra todavía abierta para el día UTC en curso.
            end -= timedelta(days=1)
        elif listing_id:
            currency = listings[listing_id].currency
            price_type = PriceType.EOD_CLOSE
        else:
            currency = instruments[instrument_id].share_class_currency
            price_type = PriceType.NAV
        if currency is None:
            continue
        try:
            price = provider.get_latest(
                symbol=symbol, instrument_id=instrument_id, listing_id=listing_id,
                currency=currency, price_type=price_type, start=start, end=end,
            )
        except HTTPError as error:
            error.close()
            if error.code == 401:
                raise MarketCredentialsRejected from None
            continue
        except (OSError, ValueError, HTTPException):
            continue
        if price is not None:
            quotes.append(price)

    fx: list[FXObservation] = []
    fx_keys = dict.fromkeys(
        (price.currency, price.price_as_of) for price in quotes
        if price.currency != portfolio.base_currency and type(price.price_as_of) is date
    )
    for currency, price_date in fx_keys:
        try:
            rate = fx_provider.get_rate(portfolio.base_currency, currency, price_date)
        except HTTPError as error:
            error.close()
            continue
        except (OSError, ValueError, HTTPException, CSVError):
            continue
        if rate is not None and rate.as_of == price_date:
            fx.append(rate)

    snapshot = value_portfolio(
        portfolio, quotes, fx,
        instruments=DEMO_INSTRUMENTS,
        listings=DEMO_LISTINGS,
        snapshot_id=str(uuid4()),
        as_of=as_of,
        calculated_at=datetime.now(timezone.utc),
        max_price_age_days=LIVE_MAX_PRICE_AGE_DAYS,
    )
    store.save(snapshot, mode="live")
    return snapshot
