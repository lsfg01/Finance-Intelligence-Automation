# Datos comunes para cartera e inteligencia — propuesta 1.1

Esta propuesta permite que la implementación simple de LLM y los futuros agentes usen las mismas entradas y salidas. Se basa en la demo actual; no sustituye el modelo de cartera que está desarrollando el compañero ni afirma que ya se haya integrado. El acuerdo final y la persistencia en el proyecto compartido corresponden a la PR conjunta.

## Archivos para intercambiar

- `ejemplos/analisis_unificado_demo.json`: entrada y salida reales del mock sobre fixtures, sin agentes ni datos reales.
- `ejemplos/analisis_unificado_v1.1.schema.json`: JSON Schema generado para la **serialización** de `AnalysisEnvelope`. Las reglas entre campos, las referencias y el corte temporal también requieren `AnalysisEnvelope.model_validate_json(...)`: el esquema JSON por sí solo no las implementa todas.
- `backend/app/intelligence/contracts.py`: definición Pydantic ejecutable.
- `backend/app/intelligence/adapters.py`: puente desde el cálculo `exposure_for_issuer()` de la demo actual.

## Formato externo

El objeto `AnalysisEnvelope` es el contenedor propuesto para intercambio o almacenamiento JSON, con tres secciones:

| Campo | Tipo | Contenido |
|---|---|---|
| `contract_version` | `"1.1"` | Versión del contenedor. |
| `context` | `AnalysisContext` | `run_id`, versiones de cartera/perfil, `as_of`, clasificación, cartera y perfil completos, documentos y exposiciones calculadas. |
| `result` | `IntelligenceResult` | Mismas referencias al snapshot, `decision`, hallazgos, argumentos, propuestas cualitativas, datos faltantes, avisos e información de implementación/modelo/prompt. |
| `contributions` | Lista de `AgentContribution` | Artefactos opcionales de pasos futuros; una ejecución sin agentes devuelve `[]`. |

Los `Decimal` se **serializan como cadenas**, por ejemplo `"3600.00"` EUR y `"51.43"` para `known_share_pct`: este último usa escala 0–100, no fracción 0–1. Cantidades y precios de cartera se reciben del snapshot; exposiciones, coincidencias y avisos de cobertura proceden de Python. `coverage_warnings[].uncovered_weight_pct` es la parte no desglosada en escala 0–100. Las fechas llevan zona horaria. No se deduce la exposición de pesos desconocidos.

Una `EvidenceRef` contiene `document_id`, `source_field` y fragmento literal. En esta demo `source_field` solo puede ser `title` o `summary`: la coincidencia se comprueba contra el documento incluido en el contexto, pero el resumen **no acredita el contenido original**. En las fuentes reales se necesitarán versión de documento, hash, fragmentos y derechos acordados. El validador tampoco demuestra que la cita fundamente la conclusión.

`decision` es `REVISAR` o `ABSTENERSE`; no es el estado de la cola. Una abstención no contiene posiciones propuestas. `proposed_positions` expresa acciones cualitativas para revisión; no contiene pesos objetivo ni ejecuta operaciones. La definición de pesos, instrumentos nuevos y el mecanismo de aprobación serán otra decisión del equipo.

## Agentes previstos y datos compartidos

Cada contribución tiene `contribution_id`, `role`, `run_id`, versiones de cartera/perfil, `as_of`, `status`, hallazgos/evidencias, avisos, datos faltantes, implementación y modelo/prompt opcionales. Los validadores comprueban que pertenezca a la misma ejecución y que sus evidencias existan en el snapshot. El identificador de contribución lo proporciona quien orquesta; el módulo no inventa identidades persistentes.

| Rol del contrato | Referencia de los repositorios revisados | Campos de trabajo |
|---|---|---|
| `news` | News Analyst de TradingAgents | `events` con tipo, descripción, candidatos de emisor, etiquetas, fecha opcional y evidencia. Son candidatos: no se han resuelto ni agrupado automáticamente. |
| `company_research` | Market Researcher de Anthropic / investigación de Dexter | `findings`, `arguments_for`, `arguments_against` y evidencia de la empresa. |
| `earnings_review` | Earnings Reviewer de Anthropic | Mismos hallazgos y evidencias; los cálculos financieros se reciben del motor externo. |
| `thesis_review` | Skill `thesis-tracker` de Anthropic | Mismos argumentos y una referencia opcional `thesis` con ID y versión. La aplicación actual todavía no almacena tesis. |
| `verification` | Fact Checker de FinResearchAgent | Hallazgos, datos que faltan y advertencias; un campo o una etiqueta de verificación no prueban por sí solos que la conclusión sea verdadera. |

Estos roles son **formatos para futuras implementaciones**, no agentes instalados ni ejecutados. `status` (`complete`, `partial`, `abstained`) describe la contribución, no cambia el estado del trabajo. `issuer_candidates` no es una resolución de empresa: puede estar vacío o contener varios candidatos. El resolvedor y el agrupamiento de noticias serán responsabilidad de la aplicación.

## Preparar y validar un intercambio

```python
from app.analysis import exposure_for_issuer
from app.intelligence import (
    AnalysisEnvelope, context_from_current_snapshot, pipeline_from_env,
)

# Datos cargados y congelados por el orquestador de la aplicación.
context = context_from_current_snapshot(
    run_id=run_id,
    portfolio_version=portfolio_version,
    profile_version=profile_version,
    as_of=as_of,
    data_classification="SIMULATED",
    portfolio=portfolio,
    profile=profile,
    documents=documents,
    exposures=[exposure_for_issuer(portfolio, issuer_id)],
)
result = pipeline_from_env().analyze(context)
envelope = AnalysisEnvelope(context=context, result=result)
payload_json = envelope.model_dump_json()
```

Para leerlo: `AnalysisEnvelope.model_validate_json(payload_json)`. La aplicación es quien podría guardar el JSON y gestionar transacciones y estados; la clase no lee ni escribe la BD. La prueba `test_intelligence_unified.py` demuestra un intercambio aislado en SQLite en memoria, no la integración con la tabla `reports` existente.

## Versionado y límites

- Esta revisión se identifica como **1.1**. El paquete anterior era una propuesta 1.0 con lectores que rechazan campos nuevos: no asumir compatibilidad silenciosa. Se aceptan contextos/resultados marcados `1.0` por separado para facilitar una transición; el `AnalysisEnvelope` exige `1.1`. La actualización y validación del nuevo contrato deben ser explícitas.
- `context_from_current_snapshot` acepta exactamente el diccionario actual de `exposure_for_issuer` y los modelos existentes. Si la nueva cartera cambia sus campos, acordar con su responsable un adaptador y pruebas; no se ha visto esa rama.
- El ejemplo contiene un snapshot de cartera y perfil. Tratar los resultados reales como información privada; no enviar datos reales a proveedores externos sin autorización ni controles adecuados.
- El esquema de BD, migrations, endpoints y worker **no se han modificado**. No hay un flujo multiagente ni deduplicación implementados. Los adaptadores de Grok/Groq se probaron con HTTP simulado; no se verificaron claves o servicios reales.
