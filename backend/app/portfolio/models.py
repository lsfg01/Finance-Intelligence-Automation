from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def reject_inexact_amount(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("use a decimal string, Decimal or integer")
    return value


def parse_calendar_date(value: object) -> object:
    if type(value) is date or (
        isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    ):
        return value
    raise ValueError("use a calendar date in YYYY-MM-DD format")


NonEmpty = Annotated[str, Field(min_length=1)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
ISIN = Annotated[str, Field(pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")]
MIC = Annotated[str, Field(pattern=r"^[A-Z0-9]{4}$")]
ExactDecimal = Annotated[Decimal, BeforeValidator(reject_inexact_amount), Field(allow_inf_nan=False)]
CalendarDate = Annotated[date, BeforeValidator(parse_calendar_date)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssetType(StrEnum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    BOND = "BOND"
    ETC_ETN = "ETC_ETN"
    CRYPTO = "CRYPTO"
    CASH = "CASH"
    OTHER = "OTHER"


class PriceType(StrEnum):
    NAV = "NAV"
    EOD_CLOSE = "EOD_CLOSE"
    LAST = "LAST"
    INDICATIVE = "INDICATIVE"
    IMPORTED = "IMPORTED"


class Instrument(DomainModel):
    instrument_id: NonEmpty
    name: NonEmpty
    asset_type: AssetType
    issuer_id: NonEmpty | None = None
    isin: ISIN | None = None
    share_class_currency: Currency | None = None
    fund_base_currency: Currency | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> Instrument:
        if self.issuer_id == self.instrument_id:
            raise ValueError("issuer_id and instrument_id must be distinct")
        if (
            self.asset_type in {AssetType.MUTUAL_FUND, AssetType.ETF}
            and self.share_class_currency is None
        ):
            raise ValueError("a fund requires a share_class_currency")
        return self


class Listing(DomainModel):
    listing_id: NonEmpty
    instrument_id: NonEmpty
    mic: MIC
    ticker: NonEmpty
    currency: Currency


class ProviderSymbol(DomainModel):
    provider: NonEmpty
    symbol: NonEmpty
    instrument_id: NonEmpty
    listing_id: NonEmpty | None = None
    verified_at: AwareDatetime


class Account(DomainModel):
    account_id: NonEmpty
    name: NonEmpty


class Position(DomainModel):
    position_id: NonEmpty
    account_id: NonEmpty
    instrument_id: NonEmpty
    listing_id: NonEmpty | None = None
    quantity: Annotated[ExactDecimal, Field(ge=0)]
    as_of: CalendarDate


class PortfolioSnapshot(DomainModel):
    snapshot_id: NonEmpty
    portfolio_id: NonEmpty
    version: Annotated[int, Field(ge=1)]
    base_currency: Currency
    accounts: tuple[Account, ...]
    positions: tuple[Position, ...]
    as_of: CalendarDate
    is_simulated: bool

    @model_validator(mode="after")
    def validate_positions(self) -> PortfolioSnapshot:
        account_ids = {account.account_id for account in self.accounts}
        if len(account_ids) != len(self.accounts):
            raise ValueError("duplicate account_id")
        if len({position.position_id for position in self.positions}) != len(self.positions):
            raise ValueError("duplicate position_id")
        if any(position.account_id not in account_ids for position in self.positions):
            raise ValueError("position refers to an unknown account")
        if any(position.as_of > self.as_of for position in self.positions):
            raise ValueError("position date is later than the snapshot date")
        return self


class Observation(DomainModel):
    observation_id: NonEmpty
    provider: NonEmpty
    source: NonEmpty
    license: NonEmpty
    retrieved_at: AwareDatetime
    is_simulated: bool

    @model_validator(mode="after")
    def validate_retrieval_timezone(self) -> Observation:
        if self.retrieved_at.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("retrieved_at must be UTC")
        return self


class MarketObservation(Observation):
    instrument_id: NonEmpty
    listing_id: NonEmpty | None = None
    value: Annotated[ExactDecimal, Field(gt=0)]
    currency: Currency
    price_type: PriceType
    price_as_of: CalendarDate | AwareDatetime

    @model_validator(mode="after")
    def validate_price_type(self) -> MarketObservation:
        is_timestamp = isinstance(self.price_as_of, datetime)
        if self.price_type == PriceType.NAV and (is_timestamp or self.listing_id is not None):
            raise ValueError("NAV requires a date and the instrument's share class")
        if self.price_type == PriceType.LAST and not is_timestamp:
            raise ValueError("LAST requires a timezone-aware timestamp")
        if self.price_type == PriceType.EOD_CLOSE and self.listing_id is None:
            raise ValueError("EOD_CLOSE requires a listing")
        return self


class FXObservation(Observation):
    """The rate is quote_currency units per one base_currency unit."""

    base_currency: Currency
    quote_currency: Currency
    rate: Annotated[ExactDecimal, Field(gt=0)]
    as_of: CalendarDate

    @model_validator(mode="after")
    def validate_pair(self) -> FXObservation:
        if self.base_currency == self.quote_currency:
            raise ValueError("FX currencies must be distinct")
        return self


class FundComposition(Observation):
    instrument_id: NonEmpty
    as_of: CalendarDate
    known_weight: Annotated[ExactDecimal, Field(ge=0, le=1)] | None = None
