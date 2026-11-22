from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.portfolio.fixtures import (
    DEMO_AS_OF,
    DEMO_BITCOIN_SYMBOL,
    DEMO_COMPOSITIONS,
    DEMO_INSTRUMENTS,
    DEMO_LISTINGS,
    DEMO_PORTFOLIO,
    FixtureMarketDataProvider,
)
from app.portfolio.models import AssetType, FXObservation, FundComposition, MarketObservation, PortfolioSnapshot, Position, PriceType


def test_fixture_positions_reference_exact_instruments_and_listings():
    instruments = {item.instrument_id: item for item in DEMO_INSTRUMENTS}
    listings = {item.listing_id: item for item in DEMO_LISTINGS}
    assert set(instruments) == {"F01", "F02", "F03", "E01", "E02", "E03", "A01", "A02", "C01", "K01", "F04"}
    assert {position.instrument_id for position in DEMO_PORTFOLIO.positions} == set(instruments)
    assert DEMO_PORTFOLIO.is_simulated
    for position in DEMO_PORTFOLIO.positions:
        assert isinstance(position.quantity, Decimal)
        if position.listing_id is not None:
            assert listings[position.listing_id].instrument_id == position.instrument_id
    assert instruments["K01"].isin is None
    assert DEMO_BITCOIN_SYMBOL.symbol == "bitcoin"
    assert DEMO_BITCOIN_SYMBOL.instrument_id == "K01"
    assert instruments["C01"].asset_type == AssetType.ETC_ETN
    assert instruments["A02"].issuer_id != instruments["A02"].instrument_id


def test_three_unlisted_fund_classes_have_separate_nav_observations():
    instruments = {item.instrument_id: item for item in DEMO_INSTRUMENTS}
    provider = FixtureMarketDataProvider()
    expected_isins = {"F01": "IE00B03HD191", "F02": "IE00BYX5NX33", "F03": "IE00B18GC888"}
    for case, isin in expected_isins.items():
        instrument = instruments[case]
        assert instrument.isin == isin
        assert instrument.asset_type == AssetType.MUTUAL_FUND
        assert not any(listing.instrument_id == case for listing in DEMO_LISTINGS)
        observation = provider.get_latest(case)
        assert observation is not None
        assert observation.is_simulated
        assert observation.currency == instrument.share_class_currency == "EUR"
        assert observation.price_type == PriceType.NAV
        assert type(observation.price_as_of) is date
        assert MarketObservation.model_validate_json(observation.model_dump_json()) == observation
    assert instruments["F02"].fund_base_currency == "USD"
    assert provider.get_latest("F04") is None


def test_same_isin_can_have_different_listing_prices_and_currencies():
    provider = FixtureMarketDataProvider()
    listings = {listing.listing_id: listing for listing in DEMO_LISTINGS if listing.instrument_id == "E01"}
    quote_xetra = provider.get_latest("E01", "E01-XETR")
    quote_london = provider.get_latest("E01", "E01-XLON")
    assert quote_xetra is not None and quote_london is not None
    assert quote_xetra.currency == listings["E01-XETR"].currency == "EUR"
    assert quote_london.currency == listings["E01-XLON"].currency == "USD"
    assert quote_xetra.value != quote_london.value
    assert quote_xetra.price_type == quote_london.price_type == PriceType.EOD_CLOSE
    assert provider.get_latest("E01") is None
    assert provider.get_latest("E02", "E01-XETR") is None


def test_position_with_unknown_listing_preserves_e01_ambiguity():
    e01 = next(position for position in DEMO_PORTFOLIO.positions if position.instrument_id == "E01")
    data = e01.model_dump(exclude={"listing_id"})
    position = Position.model_validate(data)
    restored = Position.model_validate_json(position.model_dump_json())

    assert restored.instrument_id == "E01"
    assert restored.listing_id is None
    assert {listing.listing_id for listing in DEMO_LISTINGS if listing.instrument_id == "E01"} == {
        "E01-XETR", "E01-XLON",
    }
    assert FixtureMarketDataProvider().get_latest(restored.instrument_id, restored.listing_id) is None


def test_crypto_and_fx_have_typed_dates_and_fixed_provenance():
    provider = FixtureMarketDataProvider()
    btc = provider.get_latest("K01")
    assert btc is not None and btc.is_simulated
    assert btc.price_type == PriceType.INDICATIVE
    assert isinstance(btc.price_as_of, datetime)
    assert MarketObservation.model_validate_json(btc.model_dump_json()) == btc
    fx = provider.get_rate("EUR", "USD", DEMO_AS_OF)
    assert fx is not None and fx.is_simulated
    assert fx.rate == Decimal("1.1250")
    assert fx.retrieved_at.tzinfo is timezone.utc
    assert FXObservation.model_validate_json(fx.model_dump_json()) == fx
    assert provider.get_rate("USD", "EUR", DEMO_AS_OF) is None
    assert provider.get_rate("EUR", "USD", date(2024, 1, 16)) is None


def test_composition_distinguishes_partial_unknown_and_known_zero():
    partial, unknown = DEMO_COMPOSITIONS
    assert partial.is_simulated and unknown.is_simulated
    assert partial.known_weight == Decimal("0.40")
    assert unknown.known_weight is None
    assert FundComposition.model_validate_json(unknown.model_dump_json()).known_weight is None
    assert FundComposition.model_validate({**unknown.model_dump(), "known_weight": "0"}).known_weight == Decimal("0")
    with pytest.raises(ValidationError):
        FundComposition.model_validate({**partial.model_dump(), "known_weight": "1.01"})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"price_as_of": "2024-01-15T00:00:00Z"}, "NAV requires a date"),
        ({"price_as_of": datetime(2024, 1, 15)}, "timezone"),
        ({"price_type": "LAST"}, "LAST requires"),
        ({"price_type": "EOD_CLOSE"}, "EOD_CLOSE requires a listing"),
        ({"retrieved_at": "2024-01-15T22:00:00+01:00"}, "must be UTC"),
        ({"value": 3.14}, "decimal string"),
        ({"currency": "eur"}, "pattern"),
    ],
)
def test_market_observation_rejects_invalid_price_representation(changes, message):
    nav = FixtureMarketDataProvider().get_latest("F01")
    assert nav is not None
    with pytest.raises(ValidationError, match=message):
        MarketObservation.model_validate({**nav.model_dump(), **changes})


def test_snapshot_is_immutable_and_validates_account_and_position_ids():
    snapshot = PortfolioSnapshot.model_validate_json(DEMO_PORTFOLIO.model_dump_json())
    assert snapshot == DEMO_PORTFOLIO
    with pytest.raises(ValidationError, match="frozen"):
        snapshot.version = 2
    with pytest.raises(ValidationError, match="duplicate position_id"):
        PortfolioSnapshot.model_validate({
            **snapshot.model_dump(), "positions": (snapshot.positions[0],) * 2
        })
    with pytest.raises(ValidationError, match="unknown account"):
        PortfolioSnapshot.model_validate({**snapshot.model_dump(), "accounts": ()})
