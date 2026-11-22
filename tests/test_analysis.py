from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.analysis import build_report, exposure_for_issuer
from app.fixtures import DEMO_PORTFOLIO, DEMO_PROFILE, DEMO_DOCUMENT
from app.models import Portfolio


def test_direct_and_indirect_exposure_and_partial_coverage():
    e = exposure_for_issuer(DEMO_PORTFOLIO, "DEMO:CHIP")
    assert Decimal(e["portfolio_value_eur"]) == Decimal("7000")
    assert Decimal(e["direct_eur"]) == Decimal("3000")
    assert Decimal(e["indirect_eur"]) == Decimal("600")
    assert Decimal(e["known_total_eur"]) == Decimal("3600")
    assert Decimal(e["known_share_pct"]) == Decimal("51.43")
    assert e["coverage_warnings"][0]["uncovered_weight_pct"] == "50.00"
    assert {m["kind"] for m in e["matches"]} == {"direct", "indirect"}


def test_report_does_not_generate_trading_signal():
    r = build_report(DEMO_PORTFOLIO, DEMO_PROFILE, [DEMO_DOCUMENT])
    assert r["proposal"] == "REVISAR"
    assert r["data_classification"] == "SIMULATED"
    assert r["proposal_type"] == "demostracion_no_accionable"
    assert r["evidence"][0]["document_id"] == "DOC-DEMO-001"


def test_zero_evidence_abstains():
    assert build_report(DEMO_PORTFOLIO, DEMO_PROFILE, [])["proposal"] == "ABSTENERSE"


def test_unconverted_currency_rejected():
    changed = DEMO_PORTFOLIO.model_dump(mode="json")
    changed["positions"][0]["quote_currency"] = "USD"
    with pytest.raises(ValidationError, match="sin conversion FX"):
        Portfolio.model_validate(changed)


def test_missing_composition_source_rejected():
    changed = DEMO_PORTFOLIO.model_dump(mode="json")
    changed["positions"][1]["composition_source"] = None
    with pytest.raises(ValidationError, match="fecha y procedencia"):
        Portfolio.model_validate(changed)


def test_composition_over_100_rejected():
    changed = DEMO_PORTFOLIO.model_dump(mode="json")
    changed["positions"][1]["holdings"][0]["weight"] = "0.90"
    with pytest.raises(ValidationError, match="superan el 100"):
        Portfolio.model_validate(changed)
