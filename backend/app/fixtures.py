"""Datos inventados: nunca se deben presentar como cotizaciones/noticias reales."""
from .models import Portfolio, Profile, SourceDocument

DEMO_PORTFOLIO = Portfolio.model_validate({
    "name": "Cartera ficticia de validacion",
    "base_currency": "EUR",
    "positions": [
        {"position_id": "P1", "instrument_id": "DEMO:CHIP", "name": "DemoChip S.A. (FICTICIA)",
         "kind": "stock", "quantity": "30", "unit_price": "100", "quote_currency": "EUR",
         "price_at": "2026-11-18T18:00:00+00:00", "price_source": "fixture:inventado"},
        {"position_id": "P2", "instrument_id": "DEMO:ETFTECH", "name": "ETF Demo Innovacion (FICTICIO)",
         "kind": "etf", "quantity": "20", "unit_price": "150", "quote_currency": "EUR",
         "price_at": "2026-11-18T18:00:00+00:00", "price_source": "fixture:inventado",
         "composition_as_of": "2026-11-17T00:00:00+00:00", "composition_source": "fixture:inventado",
         "holdings": [{"issuer_id": "DEMO:CHIP", "weight": "0.20"},
                      {"issuer_id": "DEMO:OTHER", "weight": "0.30"}]},
        {"position_id": "P3", "instrument_id": "DEMO:OTHER", "name": "DemoOther S.A. (FICTICIA)",
         "kind": "stock", "quantity": "10", "unit_price": "100", "quote_currency": "EUR",
         "price_at": "2026-11-18T18:00:00+00:00", "price_source": "fixture:inventado"}
    ]
})

DEMO_PROFILE = Profile.model_validate({
    "name": "Perfil demostrativo",
    "horizon": "largo plazo (10 anos)",
    "risk_tolerance": "medium",
    "constraints": ["Sin operaciones automaticas"],
    "notes": "Ejemplo sintetico para pruebas, no es asesoramiento financiero"
})

DEMO_DOCUMENT = SourceDocument.model_validate({
    "document_id": "DOC-DEMO-001",
    "title": "Escenario inventado: nueva regulacion de semiconductores",
    "summary": "Documento ficticio para verificar el enlace entre una empresa y un ETF que la incluye.",
    "source_name": "Fuente ficticia de pruebas",
    "source_kind": "demo_fixture",
    "url": None,
    "published_at": "2026-11-18T10:00:00+00:00",
    "event_at": "2026-11-18T09:00:00+00:00",
    "retrieved_at": "2026-11-20T09:00:00+00:00",
    "issuer_ids": ["DEMO:CHIP"]
})
