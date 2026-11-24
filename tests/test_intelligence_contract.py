from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest
from pydantic import ValidationError

from app.fixtures import DEMO_DOCUMENT, DEMO_PORTFOLIO, DEMO_PROFILE
from app.intelligence.contracts import (
    AnalysisContext,
    EvidenceRef,
    Exposure,
    Finding,
    IntelligenceResult,
    ProposedPosition,
    validate_result,
)


def context():
    return AnalysisContext(
        run_id="run-demo", portfolio_version=1, profile_version=1,
        as_of=datetime(2026, 11, 21, tzinfo=timezone.utc),
        data_classification="SIMULATED", portfolio=DEMO_PORTFOLIO,
        profile=DEMO_PROFILE, documents=[DEMO_DOCUMENT],
        exposures=[Exposure(issuer_id="DEMO:CHIP", portfolio_value=Decimal("7000"),
                            direct=Decimal("3000"), indirect=Decimal("600"),
                            known_total=Decimal("3600"), coverage_note="Parcial")],
    )


def result():
    citation = EvidenceRef(document_id="DOC-DEMO-001", source_field="summary", excerpt="Documento ficticio")
    return IntelligenceResult(
        run_id="run-demo", portfolio_version=1, profile_version=1,
        as_of=datetime(2026, 11, 21, tzinfo=timezone.utc),
        data_classification="SIMULATED", decision="REVISAR", implementation="mock",
        findings=[Finding(statement="Es un documento de prueba", category="source_claim", evidence=[citation])],
        proposed_positions=[ProposedPosition(instrument_id="DEMO:CHIP", action="REVISAR",
                                             rationale="Revisar el escenario", evidence=[citation])],
    )


def test_context_and_result_roundtrip_as_json():
    ctx = context()
    parsed_ctx = AnalysisContext.model_validate_json(ctx.model_dump_json())
    parsed_result = IntelligenceResult.model_validate_json(result().model_dump_json())
    assert validate_result(parsed_ctx, parsed_result) == parsed_result
    assert json.loads(ctx.model_dump_json())["exposures"][0]["known_total"] == "3600"


def test_abstain_without_evidence_or_positions():
    answer = IntelligenceResult(run_id="run-demo", portfolio_version=1, profile_version=1,
                                as_of=datetime(2026, 11, 21, tzinfo=timezone.utc),
                                data_classification="SIMULATED", decision="ABSTENERSE",
                                implementation="mock", missing_data=["Falta evidencia"])
    assert validate_result(context(), answer).proposed_positions == []


def test_reject_abstention_with_proposed_positions():
    data = result().model_dump()
    data["decision"] = "ABSTENERSE"
    with pytest.raises(ValidationError, match="abstención"):
        IntelligenceResult.model_validate(data)


@pytest.mark.parametrize("field,value", [("document_id", "unknown"), ("excerpt", "texto inventado")])
def test_reject_unverifiable_evidence(field, value):
    data = result().model_dump()
    data["findings"][0]["evidence"][0][field] = value
    with pytest.raises(ValueError):
        validate_result(context(), IntelligenceResult.model_validate(data))


def test_reject_result_from_another_snapshot():
    data = result().model_dump()
    data["portfolio_version"] = 2
    with pytest.raises(ValueError, match="portfolio_version"):
        validate_result(context(), IntelligenceResult.model_validate(data))


def test_reject_future_document():
    data = context().model_dump()
    data["as_of"] = datetime(2026, 11, 19, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="retrieved_at"):
        AnalysisContext.model_validate(data)


def test_reject_classification_that_hides_fixtures():
    data = context().model_dump()
    data["data_classification"] = "MIXED_REVIEW_REQUIRED"
    with pytest.raises(ValidationError, match="SIMULATED"):
        AnalysisContext.model_validate(data)


def test_reject_unagreed_fields_and_target_weights():
    data = result().model_dump()
    data["proposed_positions"][0]["target_weight_pct"] = "20.00"
    with pytest.raises(ValidationError, match="Extra inputs"):
        IntelligenceResult.model_validate(data)


def test_reject_external_data_mislabeled_as_simulated():
    data = context().model_dump()
    data["documents"][0]["source_kind"] = "licensed_external"
    with pytest.raises(ValidationError, match="MIXED_REVIEW_REQUIRED"):
        AnalysisContext.model_validate(data)


def test_validate_evidence_in_opposing_arguments():
    data = result().model_dump()
    data["arguments_against"] = [data["findings"][0].copy()]
    data["arguments_against"][0]["evidence"] = [{"document_id": "inexistente", "source_field": "summary", "excerpt": "x"}]
    with pytest.raises(ValueError, match="documento inexistente"):
        validate_result(context(), IntelligenceResult.model_validate(data))
