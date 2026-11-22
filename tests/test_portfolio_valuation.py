from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from app.portfolio.fixtures import (
    DEMO_AS_OF,
    DEMO_FX,
    DEMO_INSTRUMENTS,
    DEMO_LISTINGS,
    DEMO_MARKET_OBSERVATIONS,
    DEMO_PORTFOLIO,
    DEMO_RETRIEVED_AT,
)
from app.portfolio.models import PriceType
from app.portfolio.valuation import PositionIssue, ValuationSnapshot, ValuationStatus, value_portfolio
from app.portfolio.valuation_store import ValuationSnapshotStore


POSITIONS = {position.instrument_id: position for position in DEMO_PORTFOLIO.positions}
QUOTES = {quote.listing_id or quote.instrument_id: quote for quote in DEMO_MARKET_OBSERVATIONS}


def value_case(positions, quotes, rates=(), **options):
    holdings = options.pop("holdings", DEMO_PORTFOLIO).model_copy(update={"positions": positions})
    return value_portfolio(
        holdings,
        quotes,
        rates,
        **{
            "instruments": DEMO_INSTRUMENTS,
            "listings": DEMO_LISTINGS,
            "snapshot_id": "test-valuation",
            "as_of": DEMO_AS_OF,
            "calculated_at": DEMO_RETRIEVED_AT,
            **options,
        },
    )


def test_two_usd_titles_value_to_200_eur_and_missing_price_leaves_total_unknown():
    msft = POSITIONS["A02"].model_copy(update={"quantity": Decimal("2")})
    quote = QUOTES["A02-XNAS"].model_copy(update={"value": Decimal("110")})
    rate = DEMO_FX.model_copy(update={"rate": Decimal("1.10")})

    complete = value_case((msft,), (quote,), (rate,))
    assert complete.positions[0].quote_value == Decimal("220")
    assert complete.positions[0].base_value == Decimal("200")
    assert complete.total_value == complete.known_value == Decimal("200")
    assert complete.status == ValuationStatus.COMPLETE

    partial = value_case((msft, POSITIONS["F04"]), (quote,), (rate,))
    assert partial.status == ValuationStatus.PARTIAL
    assert partial.known_value == Decimal("200")
    assert (partial.valued_positions, partial.total_positions) == (1, 2)
    assert partial.total_value is None
    assert partial.positions[1].issue == PositionIssue.MISSING_PRICE
    assert partial.positions[0].price_observation_id == quote.observation_id
    assert partial.positions[0].fx_observation_id == rate.observation_id
    assert partial.price_observations == (quote,)
    assert partial.fx_observations == (rate,)
    assert partial.portfolio_snapshot_id == DEMO_PORTFOLIO.snapshot_id
    assert partial.portfolio_version == DEMO_PORTFOLIO.version
    with pytest.raises(ValidationError, match="valuation summary"):
        ValuationSnapshot.model_validate({**partial.model_dump(), "total_value": "200"})


def test_demo_fixtures_value_nav_and_listings_in_their_own_currencies():
    portfolio = DEMO_PORTFOLIO
    snapshot = value_case(portfolio.positions, DEMO_MARKET_OBSERVATIONS, (DEMO_FX,))
    rows = {row.position.instrument_id: row for row in snapshot.positions}
    assert snapshot.is_simulated
    assert snapshot.status == ValuationStatus.PARTIAL
    assert snapshot.valued_positions == 10
    assert snapshot.total_positions == 11
    assert snapshot.total_value is None
    assert rows["F02"].quote_currency == "EUR"
    assert rows["F02"].fx_observation_id is None
    assert rows["E01"].quote_value == rows["E01"].base_value == Decimal("439.50")
    assert rows["A01"].base_value == Decimal("167.45")
    assert rows["A02"].fx_observation_id == DEMO_FX.observation_id
    assert rows["K01"].base_value == Decimal("387.515625")
    assert rows["F04"].base_value is None
    assert QUOTES["E01-XLON"] not in snapshot.price_observations
    assert ValuationSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_unknown_e01_listing_stays_ambiguous_with_only_one_quote_available():
    unknown = POSITIONS["E01"].model_copy(update={"listing_id": None})
    snapshot = value_case((unknown,), (QUOTES["E01-XETR"],))
    assert snapshot.status == ValuationStatus.MISSING
    assert snapshot.positions[0].issue == PositionIssue.AMBIGUOUS_LISTING
    assert snapshot.positions[0].position.listing_id is None
    assert snapshot.price_observations == ()
    assert snapshot.total_value is None


def test_explicit_e01_listings_use_distinct_prices_and_report_missing_fx():
    london = POSITIONS["E01"].model_copy(update={"listing_id": "E01-XLON"})
    snapshot = value_case((london,), (QUOTES["E01-XETR"], QUOTES["E01-XLON"]))
    row = snapshot.positions[0]
    assert row.price_observation_id == QUOTES["E01-XLON"].observation_id
    assert row.quote_currency == "USD"
    assert row.quote_value == Decimal("486.90")
    assert row.base_value is None
    assert row.issue == PositionIssue.MISSING_FX
    assert snapshot.status == ValuationStatus.MISSING
    assert snapshot.known_value == Decimal("0")


def test_inverse_fx_multiplies_and_price_date_must_match_fx_date():
    quote = QUOTES["A02-XNAS"]
    inverse_rate = DEMO_FX.model_copy(update={
        "base_currency": "USD", "quote_currency": "EUR", "rate": Decimal("0.8"),
    })
    stale_rate = inverse_rate.model_copy(update={"as_of": DEMO_AS_OF - timedelta(days=1)})

    converted = value_case((POSITIONS["A02"],), (quote,), (inverse_rate,))
    assert converted.positions[0].base_value == Decimal("932.80")
    assert converted.fx_observations == (inverse_rate,)
    missing = value_case((POSITIONS["A02"],), (quote,), (stale_rate,))
    assert missing.positions[0].issue == PositionIssue.MISSING_FX
    assert missing.fx_observations == ()


def test_stale_prices_and_observations_from_after_cutoff_are_excluded():
    quote = QUOTES["E01-XETR"]
    one_day = timedelta(days=1)
    old = quote.model_copy(update={"price_as_of": DEMO_AS_OF - one_day})
    future = quote.model_copy(update={"observation_id": "future", "price_as_of": DEMO_AS_OF + one_day})
    late = quote.model_copy(update={
        "observation_id": "late", "retrieved_at": DEMO_RETRIEVED_AT + one_day,
    })
    inputs = (late, future, old)
    snapshot = value_case((POSITIONS["E01"],), inputs)
    assert snapshot.positions[0].issue == PositionIssue.STALE_PRICE
    assert snapshot.price_observations == ()
    allowed = value_case((POSITIONS["E01"],), inputs, max_price_age_days=1)
    assert allowed.price_observations == (old,)
    assert allowed.max_price_age_days == 1


def test_price_type_and_currency_must_match_the_instrument_and_listing():
    xetra = QUOTES["E01-XETR"]
    nav = xetra.model_copy(update={"listing_id": None, "price_type": PriceType.NAV})
    wrong_currency = xetra.model_copy(update={"currency": "USD"})
    last = xetra.model_copy(update={"price_type": PriceType.LAST, "price_as_of": DEMO_RETRIEVED_AT})
    position = POSITIONS["E01"]
    assert value_case((position,), (nav,)).positions[0].issue == PositionIssue.MISSING_PRICE
    assert value_case((position,), (wrong_currency,)).positions[0].issue == PositionIssue.PRICE_CURRENCY_MISMATCH
    snapshot = value_case((position,), (last,), listed_price_type=PriceType.LAST)
    assert snapshot.price_observations == (last,)


def test_valuation_is_reproducible_and_competing_prices_do_not_win_by_input_order():
    xetra = QUOTES["E01-XETR"]
    other = xetra.model_copy(update={"observation_id": "competing", "value": Decimal("99")})
    position = POSITIONS["E01"]
    assert value_case((position,), (xetra, xetra)) == value_case((position,), (xetra,))
    first = value_case((position,), (xetra, other))
    second = value_case((position,), (other, xetra))
    assert first == second
    assert first.positions[0].issue == PositionIssue.AMBIGUOUS_PRICE
    with localcontext() as context:
        context.prec = 2
        assert value_case((position,), (xetra,)).known_value == Decimal("439.50")


def test_snapshot_store_preserves_original_value_version_and_observations(tmp_path):
    path = tmp_path / "valuation.sqlite3"
    store = ValuationSnapshotStore(path)
    position = POSITIONS["A02"].model_copy(update={"quantity": Decimal("2")})
    quote = QUOTES["A02-XNAS"].model_copy(update={"observation_id": "quote-v1", "value": Decimal("110")})
    rate = DEMO_FX.model_copy(update={"observation_id": "fx-v1", "rate": Decimal("1.10")})
    first = value_case((position,), (quote,), (rate,))
    store.save(first)
    store.save(first)
    with pytest.raises(ValidationError, match="frozen"):
        first.positions[0].position.quantity = Decimal("20")

    new_holdings = DEMO_PORTFOLIO.model_copy(update={"snapshot_id": "v2", "version": 2})
    new_quote = quote.model_copy(update={"observation_id": "quote-v2", "value": Decimal("150")})
    new_rate = rate.model_copy(update={"observation_id": "fx-v2", "rate": Decimal("1.25")})
    conflicting = value_case((position,), (new_quote,), (new_rate,), holdings=new_holdings)
    with pytest.raises(ValueError, match="already used"):
        store.save(conflicting)
    refreshed = value_case((position,), (new_quote,), (new_rate,), holdings=new_holdings, snapshot_id="refreshed")
    store.save(refreshed)

    reopened = ValuationSnapshotStore(path)
    original = reopened.get(first.snapshot_id)
    assert original == first
    assert original.total_value == Decimal("200")
    assert original.portfolio_version == 1
    assert original.portfolio_snapshot_id == DEMO_PORTFOLIO.snapshot_id
    assert original.positions[0].price_observation_id == "quote-v1"
    assert original.positions[0].fx_observation_id == "fx-v1"
    assert original.price_observations == (quote,)
    assert original.fx_observations == (rate,)
    assert reopened.get("refreshed") == refreshed
    assert refreshed.total_value == Decimal("240")
    assert refreshed.portfolio_version == 2
    assert reopened.get("missing") is None
