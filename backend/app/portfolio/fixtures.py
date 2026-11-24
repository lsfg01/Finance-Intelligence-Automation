"""Real instrument identifiers with invented positions and market observations."""

from datetime import date, datetime, timezone

from .models import (
    Account,
    AssetType,
    FundComposition,
    FXObservation,
    Instrument,
    Listing,
    MarketObservation,
    PortfolioSnapshot,
    Position,
    PriceType,
    ProviderSymbol,
)


DEMO_AS_OF = date(2024, 1, 15)
DEMO_RETRIEVED_AT = datetime(2024, 1, 15, 22, tzinfo=timezone.utc)

DEMO_INSTRUMENTS = (
    Instrument(instrument_id="F01", name="Vanguard Global Stock Index Fund EUR Acc",
               asset_type=AssetType.MUTUAL_FUND, isin="IE00B03HD191", share_class_currency="EUR"),
    Instrument(instrument_id="F02", name="Fidelity MSCI World Index Fund P-ACC-Euro",
               asset_type=AssetType.MUTUAL_FUND, isin="IE00BYX5NX33",
               share_class_currency="EUR", fund_base_currency="USD"),
    Instrument(instrument_id="F03", name="Vanguard Global Bond Index Fund EUR Hedged Acc",
               asset_type=AssetType.MUTUAL_FUND, isin="IE00B18GC888", share_class_currency="EUR"),
    Instrument(instrument_id="E01", name="iShares Core MSCI World UCITS ETF USD Acc",
               asset_type=AssetType.ETF, isin="IE00B4L5Y983",
               share_class_currency="USD", fund_base_currency="USD"),
    Instrument(instrument_id="E02", name="Vanguard FTSE All-World UCITS ETF USD Acc",
               asset_type=AssetType.ETF, isin="IE00BK5BQT80",
               share_class_currency="USD", fund_base_currency="USD"),
    Instrument(instrument_id="E03", name="iShares Core Global Aggregate Bond UCITS ETF EUR Hedged Acc",
               asset_type=AssetType.ETF, isin="IE00BDBRDM35",
               share_class_currency="EUR", fund_base_currency="USD"),
    Instrument(instrument_id="A01", name="Iberdrola", issuer_id="IBERDROLA",
               asset_type=AssetType.EQUITY, isin="ES0144580Y14"),
    Instrument(instrument_id="A02", name="Microsoft", issuer_id="MICROSOFT",
               asset_type=AssetType.EQUITY, isin="US5949181045"),
    Instrument(instrument_id="C01", name="iShares Physical Gold ETC",
               asset_type=AssetType.ETC_ETN, isin="IE00B4ND3602"),
    Instrument(instrument_id="K01", name="Bitcoin", asset_type=AssetType.CRYPTO),
    Instrument(instrument_id="F04", name="MyInvestor Cartera Permanente FI",
               asset_type=AssetType.MUTUAL_FUND, isin="ES0156572002", share_class_currency="EUR"),
)

DEMO_LISTINGS = (
    Listing(listing_id="E01-XETR", instrument_id="E01", mic="XETR", ticker="EUNL", currency="EUR"),
    Listing(listing_id="E01-XLON", instrument_id="E01", mic="XLON", ticker="IWDA", currency="USD"),
    Listing(listing_id="E02-XETR", instrument_id="E02", mic="XETR", ticker="VWCE", currency="EUR"),
    Listing(listing_id="E03-XETR", instrument_id="E03", mic="XETR", ticker="EUNA", currency="EUR"),
    Listing(listing_id="A01-XMAD", instrument_id="A01", mic="XMAD", ticker="IBE", currency="EUR"),
    Listing(listing_id="A02-XNAS", instrument_id="A02", mic="XNAS", ticker="MSFT", currency="USD"),
    Listing(listing_id="C01-XETR", instrument_id="C01", mic="XETR", ticker="PPFB", currency="EUR"),
)

DEMO_BITCOIN_SYMBOL = ProviderSymbol(
    provider="CoinGecko", symbol="bitcoin", instrument_id="K01", verified_at=DEMO_RETRIEVED_AT
)

DEMO_ACCOUNT = Account(account_id="SIM-ACCOUNT", name="Cuenta ficticia")
DEMO_PORTFOLIO = PortfolioSnapshot(
    snapshot_id="SIM-SNAPSHOT-1",
    portfolio_id="SIM-PORTFOLIO",
    version=1,
    base_currency="EUR",
    accounts=(DEMO_ACCOUNT,),
    positions=tuple(
        Position(
            position_id=f"SIM-{instrument_id}",
            account_id=DEMO_ACCOUNT.account_id,
            instrument_id=instrument_id,
            listing_id=listing_id,
            quantity=quantity,
            as_of=DEMO_AS_OF,
        )
        for instrument_id, listing_id, quantity in (
            ("F01", None, "11.250"),
            ("F02", None, "22.375"),
            ("F03", None, "9.125"),
            ("E01", "E01-XETR", "6"),
            ("E02", "E02-XETR", "3"),
            ("E03", "E03-XETR", "50"),
            ("A01", "A01-XMAD", "17"),
            ("A02", "A02-XNAS", "4"),
            ("C01", "C01-XETR", "5"),
            ("K01", None, "0.0125"),
            ("F04", None, "2.25"),
        )
    ),
    as_of=DEMO_AS_OF,
    is_simulated=True,
)

SIMULATED_SOURCE = {
    "provider": "fixture",
    "source": "I1.1 offline fixture",
    "license": "synthetic_fixture",
    "retrieved_at": DEMO_RETRIEVED_AT,
    "is_simulated": True,
}

DEMO_MARKET_OBSERVATIONS = tuple(
    MarketObservation(
        observation_id=f"SIM-QUOTE-{listing_id or instrument_id}",
        instrument_id=instrument_id,
        listing_id=listing_id,
        currency=currency,
        value=value,
        price_type=price_type,
        price_as_of=price_as_of,
        **SIMULATED_SOURCE,
    )
    for instrument_id, listing_id, currency, value, price_type, price_as_of in (
        ("F01", None, "EUR", "47.3125", PriceType.NAV, DEMO_AS_OF),
        ("F02", None, "EUR", "15.4321", PriceType.NAV, DEMO_AS_OF),
        ("F03", None, "EUR", "84.2750", PriceType.NAV, DEMO_AS_OF),
        ("E01", "E01-XETR", "EUR", "73.25", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("E01", "E01-XLON", "USD", "81.15", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("E02", "E02-XETR", "EUR", "91.44", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("E03", "E03-XETR", "EUR", "5.43", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("A01", "A01-XMAD", "EUR", "9.85", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("A02", "A02-XNAS", "USD", "291.50", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("C01", "C01-XETR", "EUR", "40.75", PriceType.EOD_CLOSE, DEMO_AS_OF),
        ("K01", None, "EUR", "31001.25", PriceType.INDICATIVE,
         datetime(2024, 1, 15, 21, 57, tzinfo=timezone.utc)),
    )
)

DEMO_FX = FXObservation(
    observation_id="SIM-FX01",
    base_currency="EUR",
    quote_currency="USD",
    rate="1.1250",
    as_of=DEMO_AS_OF,
    **SIMULATED_SOURCE,
)

DEMO_COMPOSITIONS = (
    FundComposition(
        observation_id="SIM-COMPOSITION-E01", instrument_id="E01",
        as_of=DEMO_AS_OF, known_weight="0.40", **SIMULATED_SOURCE,
    ),
    FundComposition(
        observation_id="SIM-COMPOSITION-F03", instrument_id="F03",
        as_of=DEMO_AS_OF, **SIMULATED_SOURCE,
    ),
)


class FixtureMarketDataProvider:
    """Serve the fixed simulated snapshot and return None for absent observations."""

    def get_latest(self, instrument_id: str, listing_id: str | None = None) -> MarketObservation | None:
        return next(
            (
                item for item in DEMO_MARKET_OBSERVATIONS
                if (item.instrument_id, item.listing_id) == (instrument_id, listing_id)
            ),
            None,
        )

    def get_rate(self, base: str, quote: str, as_of: date) -> FXObservation | None:
        if (base, quote, as_of) == (DEMO_FX.base_currency, DEMO_FX.quote_currency, DEMO_FX.as_of):
            return DEMO_FX
        return None
