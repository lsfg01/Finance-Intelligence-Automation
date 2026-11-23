"""Adaptador explícito de la demo actual al contrato de inteligencia."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import AnalysisContext, Exposure


def context_from_current_snapshot(*, run_id: str, portfolio_version: int, profile_version: int,
                                  as_of: datetime, data_classification: str, portfolio: Any,
                                  profile: Any, documents: list, exposures: list[dict]) -> AnalysisContext:
    """Acepta exposición de exposure_for_issuer, sin SQL ni cálculos nuevos."""
    converted = [Exposure(issuer_id=item["issuer_id"], currency="EUR",
                          portfolio_value=item["portfolio_value_eur"], direct=item["direct_eur"],
                          indirect=item["indirect_eur"], known_total=item["known_total_eur"],
                          known_share_pct=item["known_share_pct"], matches=item["matches"],
                          coverage_warnings=item["coverage_warnings"], coverage_note=item["coverage_note"])
                 for item in exposures]
    return AnalysisContext(run_id=run_id, portfolio_version=portfolio_version, profile_version=profile_version,
                           as_of=as_of, data_classification=data_classification, portfolio=portfolio,
                           profile=profile, documents=documents, exposures=converted)
