"""Intercambio del mismo contrato entre el motor actual y roles futuros."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis import exposure_for_issuer
from app.fixtures import DEMO_DOCUMENT, DEMO_PORTFOLIO, DEMO_PROFILE
from app.intelligence import AnalysisEnvelope, AgentContribution, context_from_current_snapshot
from app.intelligence.contracts import EvidenceRef, EventCandidate, Finding, ThesisRef
from app.intelligence.pipeline import LLMPipeline, MockPipeline
from test_intelligence_pipeline import FakeProvider


def adapted_context():
    return context_from_current_snapshot(
        run_id="unified-demo", portfolio_version=1, profile_version=1,
        as_of=datetime(2026, 11, 21, tzinfo=timezone.utc), data_classification="SIMULATED",
        portfolio=DEMO_PORTFOLIO, profile=DEMO_PROFILE, documents=[DEMO_DOCUMENT],
        exposures=[exposure_for_issuer(DEMO_PORTFOLIO, "DEMO:CHIP")],
    )


def test_adapter_preserves_existing_calculations_and_coverage():
    exposure = adapted_context().exposures[0]
    assert (exposure.direct, exposure.indirect, exposure.known_total) == (
        Decimal("3000"), Decimal("600"), Decimal("3600"))
    assert exposure.known_share_pct == Decimal("51.43")
    assert exposure.coverage_warnings[0].uncovered_weight_pct == Decimal("50.00")
    assert {match.kind for match in exposure.matches} == {"direct", "indirect"}


@pytest.mark.parametrize("pipeline", [MockPipeline(), LLMPipeline(FakeProvider())])
def test_same_json_for_simple_and_mock_pipeline_and_storage(pipeline):
    ctx = adapted_context()
    result = pipeline.analyze(ctx)
    envelope = AnalysisEnvelope(context=ctx, result=result)
    payload = envelope.model_dump_json()
    # The application owns persistence. This is an isolated SQLite exchange test,
    # not a change to the demo database or an integration with its worker.
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE demo_exchange (payload TEXT NOT NULL)")
        conn.execute("INSERT INTO demo_exchange VALUES (?)", (payload,))
        stored = conn.execute("SELECT payload FROM demo_exchange").fetchone()[0]
    restored = AnalysisEnvelope.model_validate_json(stored)
    assert restored.context.run_id == restored.result.run_id == "unified-demo"
    assert json.loads(stored)["context"]["exposures"][0]["known_total"] == "3600.00"
    assert restored.result.findings[0].evidence[0].document_id == "DOC-DEMO-001"


def test_news_and_thesis_agents_share_snapshot_and_evidence():
    ctx = adapted_context()
    citation = EvidenceRef(document_id="DOC-DEMO-001", source_field="summary", excerpt="Documento ficticio")
    news = AgentContribution(contribution_id="news-1", role="news", run_id=ctx.run_id,
        portfolio_version=1, profile_version=1, as_of=ctx.as_of, status="complete", implementation="test",
        events=[EventCandidate(event_type="regulatory", description="Escenario ficticio", evidence=[citation],
                               issuer_candidates=["DEMO:CHIP"], labels=["semiconductores"])])
    thesis = AgentContribution(contribution_id="thesis-1", role="thesis_review", run_id=ctx.run_id,
        portfolio_version=1, profile_version=1, as_of=ctx.as_of, status="partial", implementation="test",
        thesis=ThesisRef(thesis_id="THESIS-DEMO", version=1),
        arguments_against=[Finding(statement="Hay un escenario para revisar", category="model_inference", evidence=[citation])],
        missing_data=["La tesis no está guardada todavía en el proyecto actual."])
    envelope = AnalysisEnvelope(context=ctx, result=MockPipeline().analyze(ctx), contributions=[news, thesis])
    assert AnalysisEnvelope.model_validate_json(envelope.model_dump_json()).contributions[1].thesis.version == 1


def test_reject_cross_run_and_unknown_evidence():
    ctx = adapted_context()
    result = MockPipeline().analyze(ctx)
    base = dict(contribution_id="v-1", role="verification", run_id="other-run", portfolio_version=1,
                profile_version=1, as_of=ctx.as_of, status="partial", implementation="test")
    with pytest.raises(ValidationError, match="run_id"):
        AnalysisEnvelope(context=ctx, result=result, contributions=[AgentContribution(**base)])
    base["run_id"] = ctx.run_id
    base["findings"] = [Finding(statement="x", category="source_claim",
        evidence=[EvidenceRef(document_id="missing", source_field="summary", excerpt="x")])]
    with pytest.raises(ValidationError, match="documento inexistente"):
        AnalysisEnvelope(context=ctx, result=result, contributions=[AgentContribution(**base)])


def test_duplicate_contributions_rejected():
    ctx = adapted_context()
    contribution = AgentContribution(contribution_id="same", role="news", run_id=ctx.run_id,
        portfolio_version=1, profile_version=1, as_of=ctx.as_of, status="abstained", implementation="test")
    with pytest.raises(ValidationError, match="contribution_id duplicado"):
        AnalysisEnvelope(context=ctx, result=MockPipeline().analyze(ctx), contributions=[contribution, contribution])


def test_previous_v1_result_stays_v1_but_envelope_requires_v1_1():
    data = adapted_context().model_dump(mode="json")
    data["contract_version"] = "1.0"
    from app.intelligence import AnalysisContext
    old_context = AnalysisContext.model_validate(data)
    old_result = MockPipeline().analyze(old_context)
    assert old_result.contract_version == "1.0"
    with pytest.raises(ValidationError, match="v1.1"):
        AnalysisEnvelope(context=old_context, result=old_result)


def test_documented_example_matches_unified_contract():
    example = Path(__file__).resolve().parents[1] / "docs/ejemplos/analisis_unificado_demo.json"
    envelope = AnalysisEnvelope.model_validate_json(example.read_text(encoding="utf-8"))
    assert envelope.contract_version == "1.1"
    assert envelope.context.data_classification == "SIMULATED"
    assert envelope.context.exposures[0].known_total == Decimal("3600.00")
    assert envelope.contributions == []


def test_adapts_existing_api_report_without_changing_its_contract(tmp_path):
    from app import db
    from app.main import create_app
    path = str(tmp_path / "demo.sqlite3")
    with TestClient(create_app(path)) as client:
        run = client.post("/api/analyses").json()
        db.process_one(path)
        state = client.get(f"/api/analyses/{run['id']}").json()
        report = client.get(f"/api/reports/{state['report_id']}").json()
        snapshot = report["input_snapshot"]
        ctx = context_from_current_snapshot(
            run_id=run["id"], portfolio_version=report["portfolio_version"],
            profile_version=report["profile_version"], as_of=datetime(2026, 11, 21, tzinfo=timezone.utc),
            data_classification=report["result"]["data_classification"],
            portfolio=snapshot["portfolio"], profile=snapshot["profile"], documents=snapshot["documents"],
            exposures=report["result"]["exposures"],
        )
        envelope = AnalysisEnvelope(context=ctx, result=MockPipeline().analyze(ctx))
        assert envelope.context.exposures[0].known_total == Decimal("3600.00")
        assert client.get(f"/api/reports/{state['report_id']}").json() == report
