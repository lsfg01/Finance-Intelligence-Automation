from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .models import DomainModel, FundComposition, Instrument, Listing, PortfolioSnapshot
from .valuation import ValuationSnapshot


class PortfolioAnalysisView(DomainModel):
    """Entrada versionada para interpretar datos de cartera ya calculados."""

    contract_version: Literal["1"]
    portfolio: PortfolioSnapshot
    valuation: ValuationSnapshot
    instruments: tuple[Instrument, ...] = ()
    listings: tuple[Listing, ...] = ()
    compositions: tuple[FundComposition, ...] = ()

    @model_validator(mode="after")
    def validate_snapshot(self) -> PortfolioAnalysisView:
        portfolio = self.portfolio
        valuation = self.valuation
        if (
            portfolio.snapshot_id,
            portfolio.portfolio_id,
            portfolio.version,
            portfolio.as_of,
            portfolio.base_currency,
            portfolio.positions,
        ) != (
            valuation.portfolio_snapshot_id,
            valuation.portfolio_id,
            valuation.portfolio_version,
            valuation.portfolio_as_of,
            valuation.base_currency,
            tuple(row.position for row in valuation.positions),
        ):
            raise ValueError("La valoración no corresponde al snapshot de cartera")

        instrument_ids = {position.instrument_id for position in portfolio.positions}
        for composition in self.compositions:
            if composition.instrument_id not in instrument_ids:
                raise ValueError("La composición pertenece a un instrumento ajeno a la cartera")
            if composition.as_of > valuation.as_of or composition.retrieved_at > valuation.calculated_at:
                raise ValueError("La composición es posterior al corte de valoración")
        return self
