"""Contratos aislados para conectar una implementación de inteligencia."""

from .adapters import context_from_current_snapshot
from .contracts import AgentContribution, AnalysisContext, AnalysisEnvelope, IntelligenceResult, validate_result
from .pipeline import LLMPipeline, MockPipeline, pipeline_from_env

__all__ = ["AgentContribution", "AnalysisContext", "AnalysisEnvelope", "IntelligenceResult",
           "context_from_current_snapshot", "validate_result", "LLMPipeline", "MockPipeline", "pipeline_from_env"]
