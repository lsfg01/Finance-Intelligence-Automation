from datetime import datetime
from uuid import uuid4

from .fixtures import DEMO_INSTRUMENTS, DEMO_LISTINGS
from .holdings import InvestingExport
from .models import DomainModel, MarketObservation, PortfolioSnapshot, PriceType
from .valuation import ValuationSnapshot, value_portfolio


class ImportedValuation(DomainModel):
    """Datos declarados por Investing, ligados a una valoración concreta de I1."""

    valuation_id: str
    export: InvestingExport


def value_import(
    portfolio: PortfolioSnapshot, export: InvestingExport, loaded_at: datetime,
) -> tuple[ValuationSnapshot, ImportedValuation]:
    rows = {(row.instrument_id, row.listing_id): row for row in export.rows}
    quotes = []
    declared = {}
    for position in portfolio.positions:
        economics = rows[position.instrument_id, position.listing_id].economics
        if economics is None:
            continue
        price = economics.current_price
        value = economics.market_value
        if value is not None and value.amount >= 0:
            declared[position.position_id] = (value.amount, value.currency)
        if price is not None and price.amount > 0:
            quotes.append(MarketObservation(
                observation_id=str(uuid4()), provider="investing.com", source="Holdings CSV · Precio actual",
                license="user_supplied_demo", retrieved_at=loaded_at, is_simulated=False,
                instrument_id=position.instrument_id, listing_id=position.listing_id,
                value=price.amount, currency=price.currency, price_type=PriceType.IMPORTED,
                price_as_of=portfolio.as_of,
            ))
    valuation = value_portfolio(
        portfolio, quotes, (), instruments=DEMO_INSTRUMENTS, listings=DEMO_LISTINGS,
        snapshot_id=str(uuid4()), as_of=portfolio.as_of, calculated_at=loaded_at,
        listed_price_type=PriceType.IMPORTED, declared_values=declared,
    )
    return valuation, ImportedValuation(valuation_id=valuation.snapshot_id, export=export)
