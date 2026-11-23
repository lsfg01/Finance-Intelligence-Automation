# Propuesta de contrato de inteligencia v1.1

Estado: propuesta para revisión conjunta. No modifica la base de datos, endpoints ni informes existentes. La integración con el worker y la persistencia requiere una PR coordinada.

El formato de intercambio v1.1, su adaptador desde la cartera actual y la propuesta para futuras contribuciones de agentes están descritos en `CONTRATO_DATOS_UNIFICADO.md`.

## Responsabilidad y uso

La aplicación carga el snapshot fijado al encolar, calcula exposiciones con el motor financiero y construye `AnalysisContext`. Una implementación simple o multiagente satisface `IntelligencePipeline.analyze(context) -> IntelligenceResult`. El integrador llama `validate_result(context, result)` antes de persistir o mostrar la salida. El módulo no accede a SQL. Existe un mock local y adaptadores de LLM opcionales; se ha probado Ollama con un modelo local real y datos ficticios. Los proveedores externos no se han probado con credenciales reales.

```python
from app.intelligence import AnalysisContext, IntelligenceResult, validate_result

context = AnalysisContext.model_validate(context_dict)
result = IntelligenceResult.model_validate(result_dict)
validate_result(context, result)
payload_json = result.model_dump_json()
```

`contract_version` predeterminada es `"1.1"` y los modelos rechazan campos desconocidos. La aplicación debe conservar el JSON íntegro, la versión del contrato y las referencias a versiones e instantánea; no se propone una tabla, migración ni modificación de `reports` en esta entrega. Las posiciones en `proposed_positions` son propuestas cualitativas para revisión humana; no son órdenes. No hay pesos objetivo en v1: su unidad, origen, reglas de suma, restricciones y autorización requieren acuerdo antes de ampliar el contrato. Los importes de entrada son `Decimal`, serializados como cadenas JSON; los resultados no contienen importes ni cantidades.

## Campos esenciales

- Entrada: `run_id`, `portfolio_version`, `profile_version`, `as_of` con zona horaria, `data_classification`, objetos actuales `portfolio`, `profile`, `documents` y `exposures` calculadas externamente. Los documentos deben tener `published_at` y `retrieved_at` no posteriores a `as_of`.
- Salida: los mismos identificadores, `as_of` y clasificación; `decision` (`REVISAR` o `ABSTENERSE`), `findings`, `arguments_for`, `arguments_against`, `proposed_positions`, `missing_data`, `warnings`, `implementation`, `model` y `prompt_version`. Los argumentos usan el mismo formato y exigencia de evidencia que los hallazgos.
- Cada hallazgo lleva `statement`, `category` (`source_claim`, `source_opinion` o `model_inference`), candidatos de emisores y evidencias. Un candidato no es un emisor resuelto. Cada posición propuesta lleva `instrument_id`, acción cualitativa, justificación, riesgos y evidencias; la aplicación debe verificar la identidad del instrumento, incluso si no estaba en cartera.
- Evidencia: `document_id`, `source_field` (`title` o `summary`) y `excerpt` que debe aparecer literalmente en el snapshot. En el modelo actual se trata de un título o resumen almacenado, no de una cita al artículo original. El contrato deberá evolucionar para almacenar versiones completas, hashes y localización de fragmentos cuando las fuentes y permisos lo permitan.
- `ABSTENERSE` admite hallazgos pero no posiciones propuestas; `REVISAR` exige al menos un hallazgo. El estado del trabajo (`queued`, `running`, `completed`, `failed`) sigue siendo responsabilidad de la aplicación y no equivale a `decision`.

La validación comprueba que el resultado y la entrada corresponden al mismo análisis/snapshot y que las evidencias citan fragmentos existentes. No demuestra que la afirmación se deduzca del fragmento, que los candidatos estén resueltos ni que el resultado sea adecuado para invertir. La aplicación y el inversor deben verificarlo. Los textos de fuentes son datos no confiables.

Ejemplo de resultado persistible, usando el fixture actual:

```json
{
  "contract_version": "1.1",
  "run_id": "run-demo",
  "portfolio_version": 1,
  "profile_version": 1,
  "as_of": "2026-11-21T00:00:00Z",
  "data_classification": "SIMULATED",
  "decision": "REVISAR",
  "findings": [{
    "statement": "El documento es una prueba ficticia.",
    "category": "source_claim",
    "issuer_candidates": [],
    "evidence": [{"document_id": "DOC-DEMO-001", "source_field": "summary", "excerpt": "Documento ficticio"}]
  }],
  "arguments_for": [],
  "arguments_against": [],
  "proposed_positions": [],
  "missing_data": ["No hay fuentes reales verificadas."],
  "warnings": ["Datos ficticios; no es una instrucción de inversión."],
  "implementation": "mock",
  "model": null,
  "prompt_version": null
}
```

## Integración posterior

1. Pactar los campos con la ampliación de cartera de la otra rama; si cambian `Portfolio`, `Profile` o `SourceDocument`, crear adaptadores de versión y repetir las pruebas.
2. Establecer cómo almacenar el snapshot y resultado junto al informe sin alterar la semántica del API ni los informes antiguos; crear migración/versionado en una PR coordinada.
3. Conectar una implementación simple y una con agentes mediante el mismo protocolo; validar la salida en el límite de aplicación. Gestionar errores de proveedor y estados parciales explícitamente.
4. Añadir un contrato separado y cálculos deterministas si el equipo decide ofrecer pesos objetivo. No enviar cartera real ni documentos protegidos a un LLM sin la autorización y controles correspondientes.

## Verificación

`python -m pytest -q` ejecuta las pruebas existentes y `tests/test_intelligence_contract.py` sin red, credenciales ni una base de datos para el módulo. Las pruebas comprueban JSON, referencias, cortes temporales y abstención. Las pruebas automáticas no prueban Docker ni una API de LLM real; se probó aparte la API local de Ollama, como se detalla en `USO_INTELIGENCIA.md`.
