# Módulo de inteligencia: demo y contrato

El worker utiliza este módulo para cada trabajo solicitado y guarda `AnalysisEnvelope` en `result.intelligence` del informe inmutable. Por defecto usa el mock; el proveedor se selecciona en el entorno del worker. Sus implementaciones devuelven `IntelligenceResult` v1.1 descrito en `PROPUESTA_CONTRATO_INTELIGENCIA_V1.md`; el contrato sigue pendiente de acuerdo con el equipo.

## Docker con modelo local

En PowerShell, desde la raíz del repositorio y con Docker Desktop arrancado:

```powershell
$env:INTELLIGENCE_PROVIDER = "ollama"
docker compose --profile intelligence up --build -d
docker compose --profile intelligence exec ollama ollama pull qwen3:1.7b
```

Después abrir http://127.0.0.1:8000 y pulsar **Analizar cartera**. La primera descarga del modelo necesita Internet. Se inicia exclusivamente por petición; si el servicio, el modelo o la respuesta fallan, el trabajo queda `failed` sin informe parcial. El modelo no recibe cantidades, perfil ni exposiciones. Para volver al mock, asignar `$env:INTELLIGENCE_PROVIDER = "mock"` y recrear el worker con `docker compose up -d --force-recreate worker`. `APP_PORT` permite cambiar el puerto de la API en caso de conflicto.

El servicio Ollama solo se añade con el perfil `intelligence`, se conecta mediante la red de Compose y no publica un puerto en el equipo. Su volumen conserva el modelo. La integración es experimental y el contrato no es una propuesta de pesos ni una orden de inversión.

Para el formato de intercambio con cartera y los roles futuros, consultar `CONTRATO_DATOS_UNIFICADO.md` y el JSON de `ejemplos/analisis_unificado_demo.json`.

## Ejecución local sin conexión

Desde la raíz del proyecto, con Python y las dependencias instaladas:

```powershell
$env:PYTHONPATH = "backend"
$env:INTELLIGENCE_PROVIDER = "mock"
python -m app.intelligence.demo
```

Para imprimir un JSON con contexto y resultado juntos, usar `python -m app.intelligence.demo --envelope`. El contexto procede de los fixtures actuales y exposiciones calculadas en Python.

Imprime en stdout un JSON. El mock devuelve resúmenes tal como fueron suministrados, con citas al snapshot; copia las etiquetas de emisores del fixture como **candidatos no resueltos**. No calcula posiciones objetivo, interpreta noticias ni simula una llamada real. Si no hay documentos se abstiene.

## Modelo local sin clave: Ollama

La demo puede ejecutar un modelo real en el propio equipo con la API local de [Ollama](https://ollama.com/download). Tras instalarlo y arrancar su servicio, descargar el modelo una vez:

```powershell
ollama pull qwen3:1.7b
```

Desde la raíz del proyecto, con Python y las dependencias instaladas:

```powershell
$env:PYTHONPATH = "backend"
$env:INTELLIGENCE_PROVIDER = "ollama"
$env:INTELLIGENCE_MODEL = "qwen3:1.7b"
$env:OLLAMA_HOST = "127.0.0.1:11434" # puerto local habitual
python -m app.intelligence.demo --envelope
```

La prueba se efectuó con una instalación portátil en el puerto **11435**. Para reutilizar esa instancia mientras siga activa, configurar `$env:OLLAMA_HOST = "127.0.0.1:11435"`. El modelo ocupa aproximadamente 1,4 GB y la primera carga puede tardar; la inferencia local no requiere clave ni pago por petición. El adaptador permite HTTP sobre loopback o el nombre `ollama` de la red de Compose. Descargar el software y modelo sí requiere Internet.

La ejecución real quedó guardada en `ejemplos/resultado_ollama_real.json`: `implementation=llm:ollama`, `model=qwen3:1.7b`, decisión `ABSTENERSE` y ninguna posición propuesta por falta de información. Los datos de entrada son ficticios; el modelo es real. Una respuesta anterior inventó un emisor candidato, por lo que se añadió una regla que rechaza candidatos no validados; la ejecución guardada pasó la validación. La prueba muestra que funciona la llamada y el contrato, no demuestra la calidad financiera del modelo ni genera una cartera objetivo. Se trata de una única llamada a un modelo, no de una integración multiagente autónoma.

## Llamada opcional a un proveedor externo

La llamada se hace únicamente al ejecutar la demo con configuración explícita. Las pruebas automáticas no requieren claves ni red. Los adaptadores aceptan solo documentos marcados como `demo_fixture`, `data_classification=SIMULATED` e identificadores de instrumento que comienzan por `DEMO:`. Esas marcas no demuestran por sí solas que el usuario no haya introducido datos reales: no incluir cartera real, datos personales ni contenido sin derechos.

**Grok de xAI** (su API es de pago según su tarifa; comprobar saldo):

```powershell
$env:PYTHONPATH = "backend"
$env:INTELLIGENCE_PROVIDER = "xai"
$env:XAI_API_KEY = "<configurar localmente>"
# Opcional: $env:INTELLIGENCE_MODEL = "grok-4.3"
python -m app.intelligence.demo
```

**Groq** (proveedor distinto; comprobar acceso y límites del plan de la cuenta):

```powershell
$env:PYTHONPATH = "backend"
$env:INTELLIGENCE_PROVIDER = "groq"
$env:GROQ_API_KEY = "<configurar localmente>"
# Opcional: $env:INTELLIGENCE_MODEL = "openai/gpt-oss-20b"
python -m app.intelligence.demo
```

Nunca incluir claves en código, archivos versionados, mensajes ni salidas. No pegar claves al compartir la demo. Todos los adaptadores envían únicamente IDs de instrumentos y títulos/resúmenes ficticios: no envían perfil, cantidades o exposiciones. El modelo recibe instrucciones para devolver un JSON sin cifras financieras; Python comprueba el esquema, referencias, que no se asignen candidatos de emisor sin validar y que los instrumentos propuestos estén en el universo de prueba. Coincidir con el texto no demuestra que el análisis esté fundamentado. La salida siempre requiere revisión humana.

La primera versión limita las posiciones propuestas a los instrumentos del snapshot. Detectar candidatos nuevos exige un catálogo y resolución de instrumentos acordados con el equipo. Tampoco calcula pesos objetivo. La API no recibe herramientas de búsqueda, navegador, ejecución ni broker. Las llamadas usan límite de 2048 tokens de salida y timeout de 60 segundos para proveedores externos o 300 segundos para Ollama; no reintentan automáticamente. Errores, límite de cuota, rechazos y salidas inválidas se comunican como fallo, sin marcar el trabajo como completado ni fabricar un resultado. Con cero documentos no se llama al proveedor.

## Integración desde código

```python
from app.intelligence import AnalysisContext, pipeline_from_env, validate_result

context = AnalysisContext.model_validate(snapshot_preparado_por_la_aplicacion)
result = pipeline_from_env().analyze(context)
validate_result(context, result)
json_para_revisar = result.model_dump_json()
```

El contexto, snapshot y cálculo los prepara la aplicación; `intelligence` no accede a SQLite. `model` y `prompt_version` quedan en el resultado si hubo llamada de LLM; la aplicación guarda el sobre completo junto al informe y no calcula costes. El campo `model_calls` de salud es `null` porque no se contabilizan llamadas.

## Pruebas

`python -m pytest -q` cubre la interfaz, la integración del worker, validación de evidencia y formatos HTTP mediante respuestas simuladas. Los tests automáticos no acreditan que una clave, modelo, plan o proveedor externo funcionen. La ejecución real con Ollama se verifica por separado.

La prueba `tests/test_intelligence_http_e2e.py` toma un informe de la API de cartera existente y llama al módulo de inteligencia a través de un servidor HTTP local que imita a xAI o Groq. El JSON generado en una ejecución de esta prueba está en `ejemplos/resultado_api_simulada.json`: es completamente ficticio y su propuesta fue escrita por el servidor de prueba, no por un LLM. Ejecutar la prueba con `python -m pytest -q tests/test_intelligence_http_e2e.py`. La prueba usa `db.process_one()` de la demo; todavía no integra inteligencia en el worker ni en la tabla de informes del proyecto.
