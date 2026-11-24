"""Demostración local: python -m app.intelligence.demo"""
import argparse
from datetime import datetime, timezone
import sys

from ..analysis import exposure_for_issuer
from ..fixtures import DEMO_DOCUMENT, DEMO_PORTFOLIO, DEMO_PROFILE
from .adapters import context_from_current_snapshot
from .contracts import AnalysisEnvelope
from .pipeline import pipeline_from_env
from .providers import ProviderError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demostración del contrato de inteligencia")
    parser.add_argument("--envelope", action="store_true", help="Incluir snapshot y resultado en un único JSON")
    args = parser.parse_args(argv)
    exposure = exposure_for_issuer(DEMO_PORTFOLIO, "DEMO:CHIP")
    context = context_from_current_snapshot(
        run_id="demo-intelligence-001", portfolio_version=1, profile_version=1,
        as_of=datetime(2026, 11, 21, tzinfo=timezone.utc), data_classification="SIMULATED",
        portfolio=DEMO_PORTFOLIO, profile=DEMO_PROFILE, documents=[DEMO_DOCUMENT],
        exposures=[exposure],
    )
    try:
        result = pipeline_from_env().analyze(context)
    except (ValueError, ProviderError) as exc:
        print(f"No se generó el análisis: {exc}", file=sys.stderr)
        return 1
    output = AnalysisEnvelope(context=context, result=result) if args.envelope else result
    print(output.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
