"""Punto de extensión para una llamada simple o un flujo con agentes."""
from typing import Protocol

from .contracts import AnalysisContext, IntelligenceResult


class IntelligencePipeline(Protocol):
    def analyze(self, context: AnalysisContext) -> IntelligenceResult:
        """Propone un resultado; el integrador debe ejecutar validate_result."""
        ...
