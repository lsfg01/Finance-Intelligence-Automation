from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.models import Profile, SourceDocument
from app.portfolio.analysis_view import PortfolioAnalysisView
from app.portfolio.holdings import HoldingsSource, Money, ProfitLoss
from app.portfolio.import_valuation import ImportedValuation
from app.portfolio.models import AssetType, DomainModel, ExactDecimal, NonEmpty
from app.portfolio.valuation import ValuationStatus


class AnalysisSelection(DomainModel):
    portfolio_id: NonEmpty
    portfolio_version: Annotated[int, Field(ge=1)]
    valuation_id: NonEmpty


class PortfolioTestInput(DomainModel):
    contract_version: Literal["1"]
    run_id: NonEmpty
    queued_at: AwareDatetime
    profile_version: Annotated[int, Field(ge=1)]
    profile: Profile
    documents: tuple[SourceDocument, ...]
    view: PortfolioAnalysisView
    source: HoldingsSource | None = None
    imported: ImportedValuation | None = None

    @model_validator(mode="after")
    def validate_cutoff(self):
        if self.view.valuation.calculated_at > self.queued_at:
            raise ValueError("La valoración es posterior al encolado")
        price_ids = {price.observation_id for price in self.view.valuation.price_observations}
        fx_ids = {rate.observation_id for rate in self.view.valuation.fx_observations}
        for row in self.view.valuation.positions:
            if row.price_observation_id is not None and row.price_observation_id not in price_ids:
                raise ValueError("La observación de precio no existe")
            if row.fx_observation_id is not None and row.fx_observation_id not in fx_ids:
                raise ValueError("La observación de FX no existe")
        if self.imported:
            holdings = {(row.instrument_id, row.listing_id): row.quantity for row in self.view.portfolio.positions}
            imported = {(row.instrument_id, row.listing_id): row.quantity for row in self.imported.export.rows}
            if imported != holdings or len(imported) != len(self.imported.export.rows):
                raise ValueError("Los datos declarados no corresponden a las posiciones")
        return self


class DirectPosition(DomainModel):
    instrument_id: NonEmpty
    name: NonEmpty
    ticker: str | None
    listing_id: str | None
    quantity: ExactDecimal
    weight_pct: ExactDecimal | None
    weight_source: Literal["declared", "calculated"] | None


class PortfolioTestResult(DomainModel):
    kind: Literal["portfolio-test"] = "portfolio-test"
    contract_version: Literal["1"] = "1"
    decision: Literal["ABSTENERSE"] = "ABSTENERSE"
    selection: AnalysisSelection
    portfolio_name: NonEmpty
    direct_positions: tuple[DirectPosition, ...]
    declared_valuation_id: str | None
    declared_total: Money | None
    open_pnl: ProfitLoss | None
    daily_pnl: ProfitLoss | None
    total_pnl: ProfitLoss | None
    valuation_coverage: ValuationStatus
    indirect_exposure_status: Literal["unknown", "no_funds"]
    funds_without_holdings: tuple[str, ...]


def analyze_portfolio_snapshot(context: PortfolioTestInput) -> PortfolioTestResult:
    view, imported = context.view, context.imported
    valuation = view.valuation
    totals = imported.export.totals if imported else None
    declared_rows = (
        {(row.instrument_id, row.listing_id): row.economics for row in imported.export.rows}
        if imported and imported.valuation_id == valuation.snapshot_id else {}
    )
    instruments = {item.instrument_id: item for item in view.instruments}
    listings = {item.listing_id: item for item in view.listings}
    direct = []
    funds = set()
    for row in valuation.positions:
        position = row.position
        instrument = instruments.get(position.instrument_id)
        listing = listings.get(position.listing_id)
        if instrument and instrument.asset_type in {AssetType.ETF, AssetType.MUTUAL_FUND}:
            # I1 compositions describe coverage but do not contain identified constituents.
            funds.add(listing.ticker if listing else instrument.name)
        declared = declared_rows.get((position.instrument_id, position.listing_id))
        weight = declared.weight_pct if declared else None
        weight_source = "declared" if weight is not None else None
        if weight is None and valuation.total_value and row.base_value is not None:
            with localcontext() as decimal_context:
                decimal_context.prec = 38
                weight = row.base_value / valuation.total_value * Decimal(100)
            weight_source = "calculated"
        direct.append(DirectPosition(
            instrument_id=position.instrument_id, name=instrument.name if instrument else position.instrument_id,
            ticker=listing.ticker if listing else None, listing_id=position.listing_id, quantity=position.quantity,
            weight_pct=weight, weight_source=weight_source,
        ))
    return PortfolioTestResult(
        selection=AnalysisSelection(portfolio_id=view.portfolio.portfolio_id, portfolio_version=view.portfolio.version,
                                    valuation_id=valuation.snapshot_id),
        portfolio_name=view.portfolio.accounts[0].name if view.portfolio.accounts else view.portfolio.portfolio_id,
        direct_positions=tuple(direct), declared_valuation_id=imported.valuation_id if imported else None,
        declared_total=totals.market_value if totals else None, open_pnl=totals.open_pnl if totals else None,
        daily_pnl=totals.daily_pnl if totals else None, total_pnl=totals.total_pnl if totals else None,
        valuation_coverage=valuation.status, indirect_exposure_status="unknown" if funds else "no_funds",
        funds_without_holdings=tuple(sorted(funds)),
    )
