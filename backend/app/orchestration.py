"""Orquestación de una ejecución; la persistencia pertenece a db."""
from datetime import datetime

from .analysis import build_report
from .intelligence.adapters import context_from_current_snapshot
from .intelligence.contracts import AnalysisEnvelope
from .intelligence.pipeline import pipeline_from_env
from .models import Portfolio, Profile, SourceDocument


def build_analysis(*, run_id: str, portfolio_version: int, profile_version: int,
                   created_at: str, portfolio: Portfolio, profile: Profile,
                   documents: list[SourceDocument], pipeline=None) -> dict:
    """Calcula la exposición y valida inteligencia sobre el snapshot de la cola."""
    report = build_report(portfolio, profile, documents)
    context = context_from_current_snapshot(
        run_id=run_id, portfolio_version=portfolio_version, profile_version=profile_version,
        as_of=datetime.fromisoformat(created_at), data_classification=report["data_classification"],
        portfolio=portfolio, profile=profile, documents=documents, exposures=report["exposures"],
    )
    pipeline = pipeline if pipeline is not None else pipeline_from_env()
    result = pipeline.analyze(context)
    report["intelligence"] = AnalysisEnvelope(context=context, result=result).model_dump(mode="json")
    return report
