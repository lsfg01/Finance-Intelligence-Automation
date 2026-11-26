from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Annotated, TypeVar

from pydantic import AwareDatetime, Field, model_validator

from .models import (
    AssetType,
    CalendarDate,
    Currency,
    DomainModel,
    ExactDecimal,
    FXObservation,
    Instrument,
    Listing,
    MarketObservation,
    NonEmpty,
    PortfolioSnapshot,
    Position,
    PriceType,
)


class ValuationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class PositionIssue(StrEnum):
    UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
    UNSUPPORTED_ASSET = "UNSUPPORTED_ASSET"
    AMBIGUOUS_LISTING = "AMBIGUOUS_LISTING"
    MISSING_LISTING = "MISSING_LISTING"
    INVALID_LISTING = "INVALID_LISTING"
    MISSING_PRICE = "MISSING_PRICE"
    STALE_PRICE = "STALE_PRICE"
    PRICE_CURRENCY_MISMATCH = "PRICE_CURRENCY_MISMATCH"
    AMBIGUOUS_PRICE = "AMBIGUOUS_PRICE"
    MISSING_FX = "MISSING_FX"
    AMBIGUOUS_FX = "AMBIGUOUS_FX"


class PositionValuation(DomainModel):
    position: Position
    quote_currency: Currency | None = None
    quote_value: ExactDecimal | None = None
    base_value: ExactDecimal | None = None
    price_observation_id: NonEmpty | None = None
    fx_observation_id: NonEmpty | None = None
    issue: PositionIssue | None = None


class ValuationSnapshot(DomainModel):
    snapshot_id: NonEmpty
    portfolio_snapshot_id: NonEmpty
    portfolio_id: NonEmpty
    portfolio_version: Annotated[int, Field(ge=1)]
    portfolio_as_of: CalendarDate
    base_currency: Currency
    as_of: CalendarDate
    calculated_at: AwareDatetime
    max_price_age_days: Annotated[int, Field(ge=0)]
    listed_price_type: PriceType
    positions: tuple[PositionValuation, ...]
    price_observations: tuple[MarketObservation, ...]
    fx_observations: tuple[FXObservation, ...]
    valued_positions: Annotated[int, Field(ge=0)]
    total_positions: Annotated[int, Field(ge=0)]
    known_value: ExactDecimal
    total_value: ExactDecimal | None
    status: ValuationStatus
    is_simulated: bool

    @model_validator(mode="after")
    def validate_summary(self) -> ValuationSnapshot:
        status, known_value, valued_positions = _summarize(self.positions)
        total_value = known_value if status == ValuationStatus.COMPLETE else None
        if (
            (self.status, self.known_value, self.valued_positions, self.total_value)
            != (status, known_value, valued_positions, total_value)
            or self.total_positions != len(self.positions)
        ):
            raise ValueError("valuation summary does not match its positions")
        return self


LISTED_ASSETS = frozenset({AssetType.EQUITY, AssetType.ETF, AssetType.ETC_ETN})
UNLISTED_PRICE_TYPES = {
    AssetType.MUTUAL_FUND: PriceType.NAV,
    AssetType.CRYPTO: PriceType.INDICATIVE,
}
_VALUATION_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)

ObservationT = TypeVar("ObservationT", MarketObservation, FXObservation)
RecordT = TypeVar("RecordT", bound=DomainModel)


def _summarize(positions: tuple[PositionValuation, ...]) -> tuple[ValuationStatus, Decimal, int]:
    values = [position.base_value for position in positions if position.base_value is not None]
    with localcontext(_VALUATION_CONTEXT):
        known_value = sum(values, Decimal("0"))
    if len(values) == len(positions):
        status = ValuationStatus.COMPLETE
    else:
        status = ValuationStatus.PARTIAL if values else ValuationStatus.MISSING
    return status, known_value, len(values)


def _latest(
    observations: Sequence[ObservationT],
    rank: Callable[[ObservationT], tuple],
) -> ObservationT | None:
    """Devuelve la observación más reciente o None si hay un empate."""
    if not observations:
        return None
    best = max(observations, key=rank)
    best_rank = rank(best)
    return best if sum(rank(item) == best_rank for item in observations) == 1 else None


def _price_date(quote: MarketObservation) -> date:
    as_of = quote.price_as_of
    return as_of.date() if isinstance(as_of, datetime) else as_of


def _price_rank(quote: MarketObservation) -> tuple[date, datetime, datetime]:
    timestamp = quote.price_as_of
    if not isinstance(timestamp, datetime):
        timestamp = datetime.combine(timestamp, datetime.min.time(), tzinfo=timezone.utc)
    return _price_date(quote), timestamp, quote.retrieved_at


def _unique_by_id(items: Iterable[RecordT], identify: Callable[[RecordT], str]) -> dict[str, RecordT]:
    result: dict[str, RecordT] = {}
    for item in items:
        item_id = identify(item)
        existing = result.setdefault(item_id, item)
        if existing is not item and existing.model_dump_json() != item.model_dump_json():
            raise ValueError(f"conflicting records with id {item_id}")
    return result


def value_portfolio(
    holdings: PortfolioSnapshot,
    quotes: Iterable[MarketObservation],
    fx: Iterable[FXObservation],
    *,
    instruments: Iterable[Instrument],
    listings: Iterable[Listing],
    snapshot_id: str,
    as_of: date,
    calculated_at: datetime,
    max_price_age_days: int = 0,
    listed_price_type: PriceType = PriceType.EOD_CLOSE,
    declared_values: Mapping[str, tuple[Decimal, str]] | None = None,
) -> ValuationSnapshot:
    """Valora una cartera congelada con las observaciones disponibles en el corte."""
    if calculated_at.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("calculated_at must be UTC")
    if not holdings.as_of <= as_of <= calculated_at.date():
        raise ValueError("as_of must fall between the holdings date and the calculation date")
    if max_price_age_days < 0:
        raise ValueError("max_price_age_days must be nonnegative")
    if listed_price_type not in {PriceType.EOD_CLOSE, PriceType.LAST, PriceType.IMPORTED}:
        raise ValueError("listed prices must use EOD_CLOSE, LAST or IMPORTED")
    if declared_values and listed_price_type != PriceType.IMPORTED:
        raise ValueError("declared values require an imported valuation")

    instruments_by_id = _unique_by_id(instruments, lambda item: item.instrument_id)
    listings_by_id = _unique_by_id(listings, lambda item: item.listing_id)
    listings_by_instrument: dict[str, list[Listing]] = defaultdict(list)
    for listing in listings_by_id.values():
        listings_by_instrument[listing.instrument_id].append(listing)

    prices_by_id = _unique_by_id(quotes, lambda item: item.observation_id)
    prices_by_key: dict[tuple[str, str | None, PriceType], list[MarketObservation]] = defaultdict(list)
    for price in prices_by_id.values():
        price_time = price.price_as_of
        if price.retrieved_at > calculated_at or _price_date(price) > as_of:
            continue
        if isinstance(price_time, datetime) and price_time > calculated_at:
            continue
        prices_by_key[price.instrument_id, price.listing_id, price.price_type].append(price)

    rates_by_id = _unique_by_id(fx, lambda item: item.observation_id)
    rates_by_pair: dict[tuple[str, str, date], list[FXObservation]] = defaultdict(list)
    for rate in rates_by_id.values():
        if rate.retrieved_at <= calculated_at:
            rates_by_pair[rate.base_currency, rate.quote_currency, rate.as_of].append(rate)

    def value_position(position: Position) -> PositionValuation:
        instrument = instruments_by_id.get(position.instrument_id)
        if instrument is None:
            return PositionValuation(position=position, issue=PositionIssue.UNKNOWN_INSTRUMENT)
        listing = listings_by_id.get(position.listing_id) if position.listing_id else None
        if position.listing_id and (listing is None or listing.instrument_id != instrument.instrument_id):
            return PositionValuation(position=position, issue=PositionIssue.INVALID_LISTING)

        if instrument.asset_type in LISTED_ASSETS:
            if listing is None:
                issue = (
                    PositionIssue.AMBIGUOUS_LISTING
                    if len(listings_by_instrument[instrument.instrument_id]) > 1
                    else PositionIssue.MISSING_LISTING
                )
                return PositionValuation(position=position, issue=issue)
            price_type, expected_currency = listed_price_type, listing.currency
        else:
            price_type = UNLISTED_PRICE_TYPES.get(instrument.asset_type)
            if price_type is None:
                return PositionValuation(position=position, issue=PositionIssue.UNSUPPORTED_ASSET)
            if listing is not None:
                return PositionValuation(position=position, issue=PositionIssue.INVALID_LISTING)
            expected_currency = instrument.share_class_currency

        candidates = prices_by_key[instrument.instrument_id, position.listing_id, price_type]
        declared = (declared_values or {}).get(position.position_id)
        if not candidates:
            if declared and declared[1] in (expected_currency, holdings.base_currency):
                amount, currency = declared
                return PositionValuation(
                    position=position, quote_currency=currency, quote_value=amount,
                    base_value=amount if currency == holdings.base_currency else None,
                    issue=None if currency == holdings.base_currency else PositionIssue.MISSING_FX,
                )
            return PositionValuation(position=position, issue=PositionIssue.MISSING_PRICE)
        compatible = [price for price in candidates if expected_currency in (None, price.currency)]
        if not compatible:
            return PositionValuation(position=position, issue=PositionIssue.PRICE_CURRENCY_MISMATCH)
        fresh = [price for price in compatible if (as_of - _price_date(price)).days <= max_price_age_days]
        if not fresh:
            return PositionValuation(position=position, issue=PositionIssue.STALE_PRICE)
        price = _latest(fresh, _price_rank)
        if price is None:
            return PositionValuation(position=position, issue=PositionIssue.AMBIGUOUS_PRICE)

        quote_value = declared[0] if declared and declared[1] == price.currency else position.quantity * price.value
        quote_details = {
            "quote_currency": price.currency,
            "quote_value": quote_value,
            "price_observation_id": price.observation_id,
        }
        base = holdings.base_currency
        if declared and declared[1] == base:
            return PositionValuation(position=position, base_value=declared[0], **quote_details)
        if price.currency == base:
            return PositionValuation(position=position, base_value=quote_value, **quote_details)

        price_date = _price_date(price)
        direct = rates_by_pair[base, price.currency, price_date]
        inverse = rates_by_pair[price.currency, base, price_date]
        available = direct or inverse
        rate = _latest(available, lambda item: (item.retrieved_at,))
        if rate is None:
            issue = PositionIssue.AMBIGUOUS_FX if available else PositionIssue.MISSING_FX
            return PositionValuation(position=position, issue=issue, **quote_details)
        base_value = quote_value / rate.rate if direct else quote_value * rate.rate
        return PositionValuation(
            position=position, base_value=base_value, fx_observation_id=rate.observation_id, **quote_details
        )

    with localcontext(_VALUATION_CONTEXT):
        positions = tuple(value_position(position) for position in holdings.positions)
    status, known_value, valued_positions = _summarize(positions)
    used_prices = tuple(prices_by_id[key] for key in sorted({
        entry.price_observation_id for entry in positions if entry.price_observation_id is not None
    }))
    used_rates = tuple(rates_by_id[key] for key in sorted({
        entry.fx_observation_id for entry in positions if entry.fx_observation_id is not None
    }))
    return ValuationSnapshot(
        snapshot_id=snapshot_id,
        portfolio_snapshot_id=holdings.snapshot_id,
        portfolio_id=holdings.portfolio_id,
        portfolio_version=holdings.version,
        portfolio_as_of=holdings.as_of,
        base_currency=holdings.base_currency,
        as_of=as_of,
        calculated_at=calculated_at,
        max_price_age_days=max_price_age_days,
        listed_price_type=listed_price_type,
        positions=positions,
        price_observations=used_prices,
        fx_observations=used_rates,
        valued_positions=valued_positions,
        total_positions=len(positions),
        known_value=known_value,
        total_value=known_value if status == ValuationStatus.COMPLETE else None,
        status=status,
        is_simulated=holdings.is_simulated or any(item.is_simulated for item in (*used_prices, *used_rates)),
    )
