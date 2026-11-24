"""Propuesta de contrato v1.1. No lee la BD ni invoca proveedores de IA."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Portfolio, Profile, SourceDocument


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExposureMatch(ContractModel):
    position_id: str = Field(min_length=1)
    kind: Literal["direct", "indirect"]
    value_eur: Decimal = Field(ge=0)
    weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    trace: str = Field(min_length=1)


class CoverageWarning(ContractModel):
    position_id: str = Field(min_length=1)
    uncovered_weight_pct: Decimal = Field(ge=0, le=100)
    composition_as_of: datetime | None = None


class Exposure(ContractModel):
    """Valores aportados por el motor financiero, no calculados por el LLM."""

    issuer_id: str = Field(min_length=1)
    currency: Literal["EUR"] = "EUR"
    portfolio_value: Decimal = Field(ge=0)
    direct: Decimal = Field(ge=0)
    indirect: Decimal = Field(ge=0)
    known_total: Decimal = Field(ge=0)
    known_share_pct: Decimal | None = Field(default=None, ge=0)
    matches: list[ExposureMatch] = Field(default_factory=list)
    coverage_warnings: list[CoverageWarning] = Field(default_factory=list)
    coverage_note: str = Field(min_length=1)


class AnalysisContext(ContractModel):
    contract_version: Literal["1.0", "1.1"] = "1.1"
    run_id: str = Field(min_length=1)
    portfolio_version: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    as_of: datetime
    data_classification: Literal["SIMULATED", "MIXED_REVIEW_REQUIRED"]
    portfolio: Portfolio
    profile: Profile
    documents: list[SourceDocument]
    exposures: list[Exposure] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot(self):
        if self.as_of.utcoffset() is None:
            raise ValueError("as_of debe incluir zona horaria")
        ids = [document.document_id for document in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document_id duplicado")
        for document in self.documents:
            for field in ("published_at", "retrieved_at"):
                date = getattr(document, field)
                if date.utcoffset() is None or date > self.as_of:
                    raise ValueError(f"{field} debe tener zona horaria y ser anterior o igual a as_of")
        if self.documents and all(d.source_kind == "demo_fixture" for d in self.documents):
            if self.data_classification != "SIMULATED":
                raise ValueError("Los documentos ficticios deben identificarse como SIMULATED")
        if any(d.source_kind == "licensed_external" for d in self.documents):
            if self.data_classification != "MIXED_REVIEW_REQUIRED":
                raise ValueError("Una fuente externa requiere MIXED_REVIEW_REQUIRED")
        return self


class EvidenceRef(ContractModel):
    document_id: str = Field(min_length=1)
    source_field: Literal["title", "summary"]
    excerpt: str = Field(min_length=1)


class Finding(ContractModel):
    statement: str = Field(min_length=1)
    category: Literal["source_claim", "source_opinion", "model_inference"]
    issuer_candidates: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ProposedPosition(ContractModel):
    """Propuesta cualitativa. La asignación numérica requiere otro contrato."""

    instrument_id: str = Field(min_length=1)
    action: Literal["REVISAR", "MANTENER", "AUMENTAR", "REDUCIR"]
    rationale: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


class IntelligenceResult(ContractModel):
    contract_version: Literal["1.0", "1.1"] = "1.1"
    run_id: str = Field(min_length=1)
    portfolio_version: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    as_of: datetime
    data_classification: Literal["SIMULATED", "MIXED_REVIEW_REQUIRED"]
    decision: Literal["REVISAR", "ABSTENERSE"]
    findings: list[Finding] = Field(default_factory=list)
    arguments_for: list[Finding] = Field(default_factory=list)
    arguments_against: list[Finding] = Field(default_factory=list)
    proposed_positions: list[ProposedPosition] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    implementation: str = Field(min_length=1)
    model: str | None = None
    prompt_version: str | None = None

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision == "ABSTENERSE" and self.proposed_positions:
            raise ValueError("Una abstención no puede contener posiciones propuestas")
        if self.decision == "REVISAR" and not self.findings:
            raise ValueError("REVISAR requiere al menos un hallazgo con evidencia")
        return self


class EventCandidate(ContractModel):
    """Candidato a acontecimiento; no implica resolución ni deduplicación."""

    event_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    issuer_candidates: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    event_at: datetime | None = None
    evidence: list[EvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_event_time(self):
        if self.event_at is not None and self.event_at.utcoffset() is None:
            raise ValueError("event_at debe incluir zona horaria")
        return self


class ThesisRef(ContractModel):
    thesis_id: str = Field(min_length=1)
    version: int = Field(ge=1)


class AgentContribution(ContractModel):
    """Formato compartido para pasos futuros; no ejecuta agentes."""

    contribution_id: str = Field(min_length=1)
    role: Literal["news", "company_research", "thesis_review", "earnings_review", "verification"]
    run_id: str = Field(min_length=1)
    portfolio_version: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    as_of: datetime
    status: Literal["complete", "partial", "abstained"]
    thesis: ThesisRef | None = None
    events: list[EventCandidate] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    arguments_for: list[Finding] = Field(default_factory=list)
    arguments_against: list[Finding] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    implementation: str = Field(min_length=1)
    model: str | None = None
    prompt_version: str | None = None


def _validate_evidence(context: AnalysisContext, items: list) -> None:
    documents = {document.document_id: document for document in context.documents}
    for item in items:
        for citation in item.evidence:
            document = documents.get(citation.document_id)
            if document is None:
                raise ValueError("Referencia a documento inexistente")
            if citation.excerpt not in getattr(document, citation.source_field):
                raise ValueError("El fragmento no coincide con el documento")


def validate_result(context: AnalysisContext, result: IntelligenceResult) -> IntelligenceResult:
    """Verifica identidad y referencias; no verifica verdad ni suficiencia de evidencia."""
    for field in ("contract_version", "run_id", "portfolio_version", "profile_version", "as_of", "data_classification"):
        if getattr(context, field) != getattr(result, field):
            raise ValueError(f"El resultado no coincide con el contexto: {field}")
    items = [*result.findings, *result.arguments_for, *result.arguments_against, *result.proposed_positions]
    _validate_evidence(context, items)
    return result


class AnalysisEnvelope(ContractModel):
    """Entrada y salida comunes para serialización; no persiste por sí mismo."""

    contract_version: Literal["1.1"] = "1.1"
    context: AnalysisContext
    result: IntelligenceResult
    contributions: list[AgentContribution] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_envelope(self):
        validate_result(self.context, self.result)
        if self.context.contract_version != self.contract_version:
            raise ValueError("El sobre requiere contexto y resultado v1.1")
        ids = [item.contribution_id for item in self.contributions]
        if len(ids) != len(set(ids)):
            raise ValueError("contribution_id duplicado")
        for item in self.contributions:
            for field in ("run_id", "portfolio_version", "profile_version", "as_of"):
                if getattr(item, field) != getattr(self.context, field):
                    raise ValueError(f"La contribución no coincide con el contexto: {field}")
            _validate_evidence(self.context, [*item.events, *item.findings,
                                               *item.arguments_for, *item.arguments_against])
        return self
