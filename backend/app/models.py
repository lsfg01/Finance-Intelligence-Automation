from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Underlying(BaseModel):
    issuer_id: str = Field(min_length=1)
    weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class Position(BaseModel):
    position_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["stock", "etf", "fund", "crypto", "commodity"]
    quantity: Decimal = Field(ge=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))
    quote_currency: str = Field(min_length=3, max_length=3)
    price_at: datetime
    price_source: str = Field(min_length=1)
    holdings: list[Underlying] = Field(default_factory=list)
    composition_as_of: datetime | None = None
    composition_source: str | None = None

    @model_validator(mode="after")
    def validate_composition(self):
        if self.kind not in {"fund", "etf"} and self.holdings:
            raise ValueError("Solo fondos y ETF pueden incluir composicion en este MVP")
        if sum((x.weight for x in self.holdings), Decimal("0")) > Decimal("1"):
            raise ValueError("Los pesos de la composicion superan el 100%")
        if len({x.issuer_id for x in self.holdings}) != len(self.holdings):
            raise ValueError("Subyacentes duplicados en la composicion")
        if self.holdings and (not self.composition_as_of or not self.composition_source):
            raise ValueError("Composicion sin fecha y procedencia")
        return self


class Portfolio(BaseModel):
    name: str = Field(min_length=1)
    base_currency: Literal["EUR"] = "EUR"
    positions: list[Position] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_positions(self):
        ids = [x.position_id for x in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificadores de posiciones duplicados")
        if any(x.quote_currency != self.base_currency for x in self.positions):
            raise ValueError("Este MVP solo calcula carteras EUR sin conversion FX; no agrega divisas incompatibles")
        return self


class Profile(BaseModel):
    name: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    risk_tolerance: Literal["low", "medium", "high"]
    constraints: list[str] = Field(default_factory=list)
    notes: str = ""


class SourceDocument(BaseModel):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_kind: Literal["demo_fixture", "licensed_external"]
    url: str | None = None
    published_at: datetime
    event_at: datetime | None = None
    retrieved_at: datetime
    issuer_ids: list[str] = Field(default_factory=list)
