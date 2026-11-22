"""Calculo determinista, con Decimal y cobertura explicita. No usa IA."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from .models import Portfolio, Profile, SourceDocument


def format_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def exposure_for_issuer(portfolio: Portfolio, issuer_id: str) -> dict:
    portfolio_total = sum((p.quantity * p.unit_price for p in portfolio.positions), Decimal("0"))
    direct = Decimal("0")
    indirect = Decimal("0")
    matched = []
    coverage_warnings = []
    for pos in portfolio.positions:
        value = pos.quantity * pos.unit_price
        if pos.instrument_id == issuer_id and pos.kind == "stock":
            direct += value
            matched.append({"position_id": pos.position_id, "kind": "direct", "value_eur": format_money(value),
                            "trace": f"{pos.position_id}: instrumento {issuer_id}"})
        if pos.kind in {"etf", "fund"}:
            known_weight = sum((h.weight for h in pos.holdings), Decimal("0"))
            uncovered = Decimal("1") - known_weight
            if uncovered:
                coverage_warnings.append({"position_id": pos.position_id,
                                          "uncovered_weight_pct": format_money(uncovered * 100),
                                          "composition_as_of": pos.composition_as_of.isoformat() if pos.composition_as_of else None})
            for h in pos.holdings:
                if h.issuer_id == issuer_id:
                    amount = value * h.weight
                    indirect += amount
                    matched.append({"position_id": pos.position_id, "kind": "indirect",
                                    "value_eur": format_money(amount),
                                    "weight_pct": format_money(h.weight * 100),
                                    "trace": f"{pos.position_id}: {h.weight} de {issuer_id}; composicion {pos.composition_source}"})
    total = direct + indirect
    return {"issuer_id": issuer_id, "portfolio_value_eur": format_money(portfolio_total),
            "direct_eur": format_money(direct), "indirect_eur": format_money(indirect),
            "known_total_eur": format_money(total),
            "known_share_pct": format_money(total / portfolio_total * 100) if portfolio_total else None,
            "matches": matched, "coverage_warnings": coverage_warnings,
            "coverage_note": "Exposicion identificada, no limite superior: la parte sin desglosar podria contener mas exposicion."}


def build_report(portfolio: Portfolio, profile: Profile, documents: list[SourceDocument]) -> dict:
    issuers = sorted({issuer for doc in documents for issuer in doc.issuer_ids})
    exposures = [exposure_for_issuer(portfolio, issuer) for issuer in issuers]
    affected = [x for x in exposures if Decimal(x["known_total_eur"]) > 0]
    no_real_sources = not documents or all(doc.source_kind == "demo_fixture" for doc in documents)
    return {
        "engine": "deterministic-demo-v0.1",
        "data_classification": "SIMULATED" if no_real_sources else "MIXED_REVIEW_REQUIRED",
        "portfolio_name": portfolio.name,
        "profile_name": profile.name,
        "currency": portfolio.base_currency,
        "exposures": exposures,
        "evidence": [{"document_id": d.document_id, "title": d.title, "summary": d.summary,
                      "source_name": d.source_name, "source_kind": d.source_kind,
                      "url": d.url, "published_at": d.published_at.isoformat(),
                      "event_at": d.event_at.isoformat() if d.event_at else None,
                      "retrieved_at": d.retrieved_at.isoformat()} for d in documents],
        "proposal": "REVISAR" if affected else "ABSTENERSE",
        "proposal_type": "demostracion_no_accionable",
        "rationale": (
            "Existe relacion documentada en los datos ficticios entre el emisor y posiciones directas/indirectas. "
            "Solo procede revisar el caso, no comprar ni vender."
            if affected else "No hay exposicion conocida suficientemente justificada; no se propone actuar."
        ),
        "arguments_for": ["La exposicion identificada es trazable a posicion y composicion" ] if affected else [],
        "arguments_against": ["La noticia y precios son ficticios; no existe evidencia externa de mercado"],
        "risks": ["Composiciones parciales pueden infravalorar la exposicion total",
                  "Valoraciones con fecha; no son precios en tiempo real"],
        "missing_data": ["Noticia real verificable y licencia de reutilizacion",
                         "Precio y composicion reales con fuente y fecha", "Evaluacion del efecto segun perfil real"],
        "revisit_if": ["Se verifican fuentes y fecha del hecho", "Cambia cartera, perfil o composicion"],
        "warnings": ["SIMULACION: datos y documentos inventados; resultado no utilizable para decisiones financieras"]
        if no_real_sources else ["La incorporacion de fuentes reales aun requiere control de calidad humano"],
        "source_statuses": [
            {"source": name, "status": "demo_success" if kind == "demo_fixture" else "provided_snapshot_unverified",
             "note": "Documento de prueba, sin consulta externa" if kind == "demo_fixture"
                     else "Solo se dispone de un snapshot suministrado, sin validar el conector"}
            for name, kind in sorted({(d.source_name, d.source_kind) for d in documents})
        ]
    }
