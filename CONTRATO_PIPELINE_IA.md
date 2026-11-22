# Contrato y ámbito de desarrollo — Pipeline de inteligencia (propuesta v0.1)

**Estado: PROPUESTA PARA REVISIÓN. No es un contrato ya implementado.**  
**Fecha:** 2026-11-22  
**Responsables:** desarrollo de inteligencia (módulo aislado) + equipo (integración compartida).

Este documento define qué puede implementar independientemente quien investiga un framework de agentes, sin bloquear ni invadir la evolución de cartera, API, fuentes y persistencia. Complementa al `AGENTS.md` de la raíz.

## 1. Estado REAL de la demo v0.1.1

```text
frontend/index.html
    └── POST /api/analyses (sin body)
         └── main.py: db.create_run()
              └── analysis_runs { id, status, portfolio_version, profile_version, documents_json, ... }
                  └── worker.py -> db.process_one()
                      ├── lee portfolio_versions y profile_versions
                      ├── decodifica documents_json
                      └── analysis.py: build_report(portfolio, profile, documents)
                          ├── extrae issuer_ids YA ETIQUETADOS en cada documento
                          ├── exposure_for_issuer() con Decimal
                          └── informe con textos prefijados y propuesta REVISAR/ABSTENERSE
                      └── guarda reports + estado completed/failed
```

No existe un prompt almacenado en la tabla `analysis_runs`; contiene una solicitud de ejecución con referencias a versiones y un snapshot documental. `worker.py` solo implementa el sondeo, y `db.py` mezcla persistencia con orquestación. El perfil aún no condiciona las propuestas. No hay interpretación semántica ni conexión a LLM.

## 2. Objetivo del módulo de inteligencia

Recibir evidencia y contexto preparado por la aplicación; **extraer hechos/emisores**, organizar relaciones con evidencia, recibir exposiciones calculadas de manera determinista, formular escenarios y propuestas cualitativas justificadas, y devolver una salida validable. No ejecutar operaciones ni determinar por sí mismo saldos, pesos, FX o valores de posición.

### Responsabilidades propuestas

| Inteligencia (ámbito propio) | Aplicación y cálculo (ámbito ajeno) |
|---|---|
| Normalizar hechos y relaciones emisor-documento, con referencia de evidencia | Cargar datos desde BD, mantener snapshots/versiones |
| Separar hechos, opinión editorial e inferencias | Resolver identificadores instrumentales con datos maestros |
| Recuperar/seleccionar evidencia pertinente y contradictoria | Realizar cálculos de exposición, importes, FX y cobertura |
| Redactar argumentos a favor/en contra, escenarios y abstención | Validar cantidades y que las citas referencien documentos existentes |
| Evaluar prompts, modelos y eventual orquestación de agentes | Guardar informe, actualizar estado, progreso y errores |

La identificación de entidades mediante IA puede producir **candidatos**. No debe tratarlos automáticamente como instrumentos inequívocos ni introducirlos como vínculos financieros confirmados.

## 3. Contratos propuestos (a diseñar/validar, NO congelados)

Se propone definir esquemas Pydantic tipados en un módulo neutral de contratos; su ruta final será objeto de acuerdo. Como referencia conceptual:

```python
class AnalysisContext(BaseModel):
    contract_version: str            # p.ej. "1"
    run_id: str
    portfolio_version: int
    profile_version: int
    portfolio: Portfolio             # existente en models.py
    profile: Profile                 # existente en models.py
    documents: list[SourceDocument]  # existente en models.py
    # En etapas siguientes: snapshot de precios/FX/holdings,
    # ventana temporal, fuentes, estado de cobertura, configuración.

class EvidenceLink(BaseModel):
    document_id: str
    issuer_id: str | None
    statement: str                   # hecho o afirmación atribuida
    category: str                    # hecho / opinión de fuente / inferencia

class IntelligenceFinding(BaseModel):
    issuer_ids: list[str]
    evidence_document_ids: list[str]
    reasoning: str
    arguments_for: list[str]
    arguments_against: list[str]
    risks: list[str]
    missing_data: list[str]
    proposed_action: str             # cualitativo, enum pendiente
    # Exposiciones NUMÉRICAS: se inyectan desde motor financiero;
    # nunca se generan como números libres desde LLM.
```

**Estos fragmentos son bocetos, no firmas de implementación ni esquemas aprobados.** Para los primeros experimentos, pueden mantenerse en un paquete aislado hasta que una PR de contratos los adopte.

Se recomienda dividir lógicamente el trabajo en dos interfaces, aunque internamente use un único flujo o varios agentes:

1. **Extracción:** `extract(documentos) -> hechos_y_candidatos`, con `document_id` y fragmento/evidencia identificable.
2. **Interpretación:** `interpret(hechos_validados, exposiciones_calculadas, perfil) -> hallazgos_cualitativos`, sin alterar los datos financieros de entrada.

Un orquestador de aplicación, no el módulo de agentes, compone ambas etapas, consulta el motor determinista y valida la salida. Los nombres y esquemas exactos se acordarán en una PR pequeña de contrato.

## 4. Política de implementación aislada

**Permitido sin tocar componentes compartidos:**

- Crear `backend/app/intelligence/` (estructura interna a criterio del responsable).
- Añadir prompts versionados, modelos de salida del módulo, adaptadores de LLM, evaluaciones y fixtures.
- Crear `tests/test_intelligence_*.py`, incluyendo mocks que no llamen servicios externos.
- Comparar baseline monoflujo vs agentes; documentar coste, latencia, calidad y limitaciones.

**Requiere una PR de integración coordinada con el equipo:**

- Modificar `backend/app/db.py`, `backend/app/worker.py`, `backend/app/main.py` o `backend/app/models.py`.
- Cambiar la forma de los trabajos `analysis_runs`, del reporte persistido o de los endpoints.
- Reemplazar `analysis.build_report()` como implementación que consume el worker.
- Introducir un framework común, un proveedor de pago, secretos o dependencias de infraestructura.

**Prohibido:**

- Operar con credenciales de bróker; ejecutar compras/ventas.
- Consultar/escribir directamente SQLite desde un agente.
- Obtener datos reales mediante scraping no autorizado.
- Alterar exposiciones o porcentajes calculados para que coincidan con una narrativa.
- Convertir una inferencia del LLM en hecho sin verificar o inventar citas.

## 5. Cómo hacer la futura integración

1. Aprobar el contrato de entrada/salida y los tests de contrato; crear un adaptador que lea el snapshot de `analysis_runs`.
2. Aislar la orquestación que hoy reside en `db.process_one()`, preservando la semántica de `queued -> running -> completed/failed`.
3. El orquestador invoca extracción, resuelve entidades, solicita cálculos a `analysis.py` (o sucesor determinista), invoca interpretación y valida trazabilidad.
4. Persistencia guarda el resultado y snapshots originales; los informes antiguos no se reinterpretan ni modifican.
5. Mantener modo de demostración determinista y fallback/abstención cuando la IA esté deshabilitada o falle. No declarar `completed` si faltan resultados críticos sin representar ese estado parcial o error.
6. Integración en PR separada de la implementación experimental de agentes, con tests unitarios y end-to-end de cola/informe.

El cambio a PostgreSQL u otra cola no debe obligar a modificar la interfaz del módulo de inteligencia. Los cambios del contrato sí requieren adaptación explícita y versionada.

## 6. Primera tarea sugerida para Codex (inteligencia)

> Implementar únicamente un **prototipo aislado de extracción e interpretación** bajo `backend/app/intelligence/` con entrada de datos ficticios. Crear un baseline simple (sin requerir un framework multiagente). Extraer posibles emisores/hechos de documentos y producir hallazgos estructurados con IDs de evidencia; representar ambigüedad y abstención. Añadir tests deterministas con mocks; documentar las interfaces propuestas. **No modificar** `db.py`, `worker.py`, `main.py`, `models.py`, el frontend ni `analysis.py`, y **no conectar** todavía el flujo a `POST /api/analyses`. Preparar una propuesta de integración como documento o PR independiente.

### Criterios de aceptación de esta primera tarea

- El paquete se importa y prueba sin Docker, base de datos, acceso a Internet ni credenciales reales.
- Los datos demo se identifican explícitamente como simulados.
- La extracción devuelve evidencia con `document_id` existente, no URLs inventadas; detecta ausencia o ambigüedad de emisor.
- La interpretación no genera cantidades monetarias nuevas y puede abstenerse.
- Ninguna prueba necesita un LLM externo; los experimentos online son opcionales, explícitos y no forman parte de CI.
- Baseline reproducible y métricas mínimas definidas para comparar enfoques.
- La PR modifica solo el módulo propio, tests y documentación relacionada.

## 7. Preguntas que el equipo debe decidir antes de la PR de integración

- Esquema/versionado concreto de `AnalysisContext` y salida del informe.
- Mapa de emisores e identificadores: qué produce IA y qué valida el resolvedor determinista.
- Ubicación e interfaz del orquestador, sin introducir SQL en inteligencia.
- Política de errores parciales y límites de coste/tokens/latencia.
- Lista mínima de casos de evaluación, resultados esperados y umbral para adoptar agentes.
- Modelo/proveedor: comparar resultados primero; no fijar uno por anticipado.

Hasta acordarlas, el trabajo de investigación e implementación aislada puede continuar sin crear deuda de integración.
