# Plan de arquitectura e implementación

Fecha: 20-11-2026. Basado en la especificación inicial de 16-11-2026. Las elecciones de esta página son propuestas técnicas, no acuerdos del equipo.

## Invariantes del producto

- La aplicación informa y propone para aprobación humana; nunca ejecuta órdenes en el MVP.
- Una pulsación explícita inicia una ejecución. Actualizar cartera no implica iniciar análisis de noticias.
- Informes inmutables: deben fijar versiones de cartera, perfil, noticias, precios, FX y composiciones.
- Separar las cifras calculadas con código de la interpretación creada por IA.
- Cada afirmación debe poder asociarse a documento/URL, fecha de publicación, fecha del hecho, fecha de captura, fecha de vigencia y grado de cobertura.
- El sistema puede abstenerse; no inferir exposición a partir de pesos desconocidos.
- Documentos externos como datos no confiables: las instrucciones embebidas no autorizan operaciones/herramientas.

## Arquitectura objetivo (MVP)

```text
React + TypeScript (dashboard + chat, siguiente incremento)
  ↓ HTTPS API con contratos tipados
FastAPI (cartera, perfiles, fuentes, ejecuciones, informes, chat)
  ↓                                  ↓
PostgreSQL + objetos/documentos     Cola de trabajos / worker
versiones, snapshots, informes          ↓
                                    Ingesta de fuentes autorizadas
                                      ↓ deduplicación + metadatos
                                    Normalización y enlazado a emisor
                                      ↓
                                    Precios/FX/holdings fechados
                                      ↓
                                    Motor deterministic exposures
                                      ↓
                                    Recuperación de evidencia filtrada
                                      ↓
                                    LLM solo para interpretación y redacción
                                      ↓ validación de citas y propuestas
                                    Informe congelado
```

En el incremento 0.1 el backend y worker existen, pero usan SQLite y fixtures; la interfaz es HTML/JS local. Se conserva la separación API/worker para no casar el producto con un servicio externo. No se usa `BackgroundTasks` de FastAPI para trabajos de análisis prolongados.

## Modelo lógico propuesto

- `instrument(id, kind, ISIN/ticker/FIGI, currency, issuer_id)` y `alias` para resolución sin confundir ticker con identidad global.
- `portfolio` + `portfolio_version` + `position_snapshot` (cantidad, valoración, mercado, origen).
- `contribution_plan` separado de posiciones ejecutadas.
- `profile_version` (objetivos, horizonte, tolerancia, restricciones, texto original).
- `price_snapshot` y `fx_snapshot` (as_of y proveedor; conversión sin datos => cifra no agregable).
- `holdings_snapshot` (instrumento colectivo, as_of, fuente, posiciones conocidas, porcentaje cubierto).
- `source_definition` y `source_attempt` (éxito parcial o error, ventana temporal, cursor solo tras éxito).
- `document` (URL/identificador, hash, publicado, hecho, obtenido, derechos, origen, contenido permitido).
- `analysis_run` (estado, progreso, fallos, versiones, coste, tokens, latencia).
- `analysis_report`, `finding`, `citation`, `exposure_calculation` (salida inmutable, trazabilidad).
- `chat_thread` y `chat_message` referenciando un `report_id`; una búsqueda nueva se etiqueta como tal.

**Contrato esencial de procedencia:** nunca normalizar un valor económico sin preservar unidad, fecha de validez y fuente. Composición parcial: distinguir `known_weight` de `uncovered_weight`; exposición conocida no es exposición total ni necesariamente límite superior.

## API objetivo

```text
POST /v1/portfolios/imports                 carga CSV/manual validada con preview
GET  /v1/portfolios/{id}/versions/{version}
PUT  /v1/portfolios/{id}                 crea nueva versión
PUT  /v1/profiles/{id}                   crea nueva versión
GET  /v1/sources                         fuentes y estado de licencia
POST /v1/analyses                        encola bajo demanda (202 + run_id)
GET  /v1/analyses/{id}                   progreso y fallos por fuente
GET  /v1/reports/{id}                    snapshot + conclusiones
POST /v1/reports/{id}/questions           respuesta limitada al informe, o modo nueva consulta etiquetado
```

El incremento 0.1 usa rutas `/api/*` simplificadas; migrar a `/v1/*` con OpenAPI versionado antes de consumirlas desde un frontend React definitivo.

## Pipeline objetivo: una ejecución de análisis

1. Persistir versiones vigentes e instantánea de configuración y fuentes. Emitir `run_id`.
2. Recuperar documentos solo desde última ejecución satisfactoria por fuente, o ventana manual. Registrar intentos y fallos por separado.
3. Normalizar fecha del hecho, fecha de publicación, emisor(s), tipo de hecho y hash; deduplicar sin eliminar procedencia.
4. Resolver emisor → identificadores financieros; calcular exposición directa y subyacente a través de holdings **fechados**.
5. Calcular valoraciones y FX con `Decimal`; si faltan FX o valoraciones, devolver indeterminado parcial, no sumar.
6. Recuperar y adjuntar evidencia verificable; separar hechos, opinión editorial e inferencia.
7. Crear hallazgos y escenarios cualitativos; argumentar a favor/en contra y permitir `ABSTENERSE`.
8. Validar que cada afirmación factual tiene cita y que toda exposición deriva de cálculo; guardar el informe como inmutable.
9. Emitir estado `completed` o `partial`/`failed` sin avanzar el cursor de fuentes fallidas.

## Decisiones tecnológicas recomendadas

| Capa | Etapa 1 | Evolución condicionada |
|---|---|---|
| Backend | Python, FastAPI, Pydantic | Mismo stack |
| Frontend | HTML/JS demo → React, TypeScript, Vite | React si aporta valor de UX |
| BD | SQLite solo demo | PostgreSQL + Alembic antes de varios usuarios |
| Tareas | Worker independiente simple | Postgres-backed jobs o Redis+RQ/Celery tras medir escala |
| Fuentes | Fixtures autorizados + 1/2 conectores verificados | Adaptadores por fuente, con cumplimiento contractual |
| Búsqueda | SQL + filtros por tiempo, fuente, emisor | `pgvector`/RAG si la evaluación lo justifica |
| IA | Un LLM con salida JSON validada, sin llamadas directas a proveedores no verificados | Modelos comparados mediante benchmark; multiagente solo si mejora resultados |
| Operación | Docker Compose local, pruebas | CI, telemetría, gestión de secretos, hosting |

## Backlog incremental sugerido

| Iteración | Resultado observable | Criterio de salida |
|---|---|---|
| I0 (entregado) | Cartera/perfil demo, exposición directa + ETF, cola, informe congelado | Tests de cálculo/versiones, botón manual, sin claves |
| I1 | Importación CSV con preview, identificadores, restricciones editables, UI React | Importar cartera y detectar datos inválidos sin perder versiones |
| I2 | 1–2 adaptadores autorizados + precio/holdings/FX | Documentos reales con procedencia, fallos visibles, fechas correctas |
| I3 | Interpretación LLM con esquema cerrado y fuentes ancladas | Contradicciones, abstención y validación de citas en dataset de evaluación |
| I4 | Chat anclado a informe e histórico | Explica y cuestiona un informe sin cambiar su contexto |
| I5 | Seguridad, despliegue, métricas y documentación | Demo reproducible, costes y latencia monitorizados, acceso controlado |

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| No hay acceso API al bróker | Bloqueo de carga real | CSV/manual como primera vía, adaptadores posteriores |
| Scraping no autorizado | Legal/operativo | Verificar ToS/licencias y usar alternativa autorizada |
| Holdings parciales / desactualizados | Exposición equivocada | Mostrar cobertura y fecha; no inventar restante |
| FX/valores stale | Cifras incorrectas | UTC + `as_of` + tasa FX explícita, no mezclar cotizaciones |
| Alucinación o citas falsas | Recomendaciones erróneas | Contrato estructurado + comprobación de citas + abstención |
| Prompt injection en artículos | Exfiltración / desvío | Fuentes como datos, herramientas con permisos mínimos |
| Scope creep (agentes/RAG/precios predictivos) | Retraso | Benchmark previo y criterios de entrada explícitos |
| Servicio expuesto sin autenticación | Fuga de carteras | Mantener I0 local; autenticación antes de entorno público |

## Evaluación

- Cálculo: casos de referencia con valores esperados (directo, indirecto, parcial, FX ausente).
- Extracción: exactitud de entidad/fecha y documentos duplicados.
- Recuperación: precisión de documentos y fecha, contra consultas benchmark.
- Generación: presencia de citas verificables, separación hecho/inferencia y abstención.
- Operación: duraciones por etapa, tokenización y coste por informe, tasas de fallos por fuente.

## Perímetro regulatorio (decisión de producto, no solo implementación)

Si el producto deja de ser una herramienta privada de investigación y ofrece recomendaciones personalizadas a terceros sobre instrumentos financieros, hay que evaluar con asesoría especializada las obligaciones aplicables en España/UE (por ejemplo MiFID II, idoneidad, prestación de asesoramiento y protección de datos). El hecho de requerir revisión humana o añadir una advertencia no resuelve por sí solo la clasificación regulatoria. La demo actual no da consejos de inversión reales.

## Costes y límites presupuestarios

El primer incremento es offline y no requiere licencias de mercado ni llamadas a un modelo. Para producción, estimar por separado (a) datos de precios/FX y sobre todo holdings con licencia, (b) coste de LLM por número de documentos, tokens y análisis, (c) almacenamiento/hosting/worker, (d) observabilidad y mantenimiento. No fijar cuotas numéricas de proveedores sin seleccionar plan, volumen y derechos de reutilización. Establecer antes de I2 un máximo por análisis, presupuesto mensual, tamaño máximo del corpus por ejecución y retención por usuario.

## Fuera del alcance de etapa 1

Ejecución de órdenes, recomendaciones cuantitativas de peso objetivo, predicción de rentabilidad, monitorización continua, integraciones mediante credenciales del bróker no documentadas, multiusuario público sin seguridad.
