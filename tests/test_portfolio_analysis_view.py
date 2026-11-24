from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.portfolio.analysis_view import PortfolioAnalysisView
from app.portfolio.valuation import PositionIssue, ValuationStatus


FIXTURE = Path(__file__).parent / "fixtures" / "portfolio_analysis_v1.json"


@pytest.fixture
def view():
    return PortfolioAnalysisView.model_validate_json(FIXTURE.read_bytes())


def test_consumer_reads_v1_from_frozen_json_without_application_services(view):
    assert view.contract_version == "1"
    assert view.portfolio.is_simulated and view.valuation.is_simulated
    assert view.portfolio.version == view.valuation.portfolio_version == 1
    assert view.valuation.status == ValuationStatus.PARTIAL
    assert (view.valuation.valued_positions, view.valuation.total_positions) == (2, 3)
    assert view.valuation.total_value is None
    assert isinstance(view.valuation.known_value, Decimal)
    assert len(view.valuation.fx_observations) == 1
    rate = view.valuation.fx_observations[0]
    london = next(row for row in view.valuation.positions if row.position.listing_id == "E01-XLON")
    assert london.quote_currency == "USD" and london.fx_observation_id == rate.observation_id
    assert view.valuation.positions[-1].issue == PositionIssue.MISSING_PRICE
    by_instrument = {item.instrument_id: item.known_weight for item in view.compositions}
    assert by_instrument == {"E01": Decimal("0.40"), "F03": None}
    assert PortfolioAnalysisView.model_validate_json(view.model_dump_json()) == view

    with pytest.raises(ValidationError, match="frozen"):
        view.portfolio.positions[0].quantity = Decimal("0")
    with pytest.raises(ValidationError, match="frozen"):
        view.valuation.price_observations[0].value = Decimal("1")


def test_v1_requires_version_and_rejects_unknown_versions(view):
    with pytest.raises(ValidationError, match="contract_version"):
        PortfolioAnalysisView.model_validate(view.model_dump(exclude={"contract_version"}))
    with pytest.raises(ValidationError, match="contract_version"):
        PortfolioAnalysisView.model_validate({**view.model_dump(), "contract_version": "2"})


def test_view_cannot_combine_valuation_with_different_portfolio_version_or_positions(view):
    data = view.model_dump()
    data["portfolio"]["version"] += 1
    with pytest.raises(ValidationError, match="no corresponde"):
        PortfolioAnalysisView.model_validate(data)

    data = view.model_dump()
    data["portfolio"]["positions"][0]["quantity"] = "99"
    with pytest.raises(ValidationError, match="no corresponde"):
        PortfolioAnalysisView.model_validate(data)


def test_view_rejects_composition_discovered_after_cutoff(view):
    data = view.model_dump()
    data["compositions"][0]["retrieved_at"] = view.valuation.calculated_at + timedelta(seconds=1)
    with pytest.raises(ValidationError, match="posterior al corte"):
        PortfolioAnalysisView.model_validate(data)
