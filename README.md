# Finance Intelligence Automation

**Demo local con tenencias y noticias ficticias.** Funciona offline por defecto con precios e inteligencia simulados. El refresco de mercado opcional consulta EODHD y el BCE bajo demanda. El worker puede usar un modelo local con Ollama.

El [punto de entrada para agentes](AGENTS.md) recoge el estado de los módulos y las lecturas por tarea. El histórico conserva el [cierre de I1](docs/historico/I1/CIERRE_I1_CARTERA_Y_PRECIOS.md) y la [aceptación de la demo de Investing.com](docs/historico/cartera/CIERRE_DEMO_INVESTING.md).

## Arranque rápido con Docker (API + worker)

```bash
docker compose up --build
```

Abrir http://127.0.0.1:8000. La documentación OpenAPI está en http://127.0.0.1:8000/docs.

## Alternativa sin Docker

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
# Terminal 1
uvicorn app.main:app --reload
# Terminal 2: desde la misma carpeta, con entorno activado
python -m app.worker
```

`DB_PATH` es opcional; por defecto se utiliza `.local/portfolio.sqlite3`. Para reiniciar la demo, parar servicios y eliminar el archivo de SQLite local (o `docker compose down -v` para el volumen de Docker).

## Verificación

```bash
pytest -q
```

## Qué funciona

- Cartera histórica I0 y perfil editables por API. Cada edición crea una versión.
- Composiciones de ETF con fuente y fecha y con parte conocida/incompleta.
- Endpoint `POST /api/analyses` que **encola** un trabajo. Ningún análisis se ejecuta sin acción explícita.
- Worker independiente que procesa solo trabajos encolados, con estado consultable.
- Cálculo de exposición directa/indirecta exacto con `Decimal`, sin mezclar divisas sin FX.
- Informe persistido e inmutable ligado a versión de cartera, perfil y snapshot documental.
- Dashboard con importación y selección de carteras de Investing.com Holdings. **Analizar cartera** fija la versión y valoración visibles y genera un informe de prueba en el worker. **Actualizar precios** solicita una nueva valoración de mercado a demanda.

## Limitaciones deliberadas de este incremento

Quedan fuera de esta entrega el chat, la autorización de usuarios, la exportación de informes, la búsqueda histórica/RAG, las alertas, las métricas de costes y el despliegue público. La cola SQLite es solo para un worker local en demostración. La API de I0 permite crear versiones de la cartera y del perfil. Los informes son para revisión humana.

El worker incorpora el resultado de inteligencia al informe, en `result.intelligence`, sin alterar las exposiciones deterministas. Por defecto utiliza el mock; el modelo local Ollama es opcional y solo acepta datos de demostración. Véanse [uso de inteligencia](docs/inteligencia/USO_INTELIGENCIA.md) y [contrato v1.1](docs/inteligencia/CONTRATO_DATOS_UNIFICADO.md).

**No exponer esta demo directamente a Internet:** los endpoints de escritura no tienen autenticación.

## API

| Método | Ruta | Efecto |
|---|---|---|
| `GET` | `/api/health` | Estado y modo de ejecución |
| `GET`, `PUT` | `/api/portfolio` | Leer o crear una versión de la cartera histórica I0 |
| `GET` | `/api/portfolio/holdings` | Listar las carteras multiactivo disponibles |
| `POST` | `/api/portfolio/investing/preview`, `/api/portfolio/investing/confirm` | Revisar un CSV de Holdings y confirmar el archivo revisado |
| `GET` | `/api/portfolio/alpaca/authorize`, `/api/portfolio/alpaca/callback` | Autorizar la conexión OAuth de solo lectura en Paper |
| `POST` | `/api/portfolio/alpaca/sync` | Crear una versión de las posiciones abiertas de la cuenta Paper conectada |
| `GET` | `/api/portfolio/valuation` | Leer las tenencias seleccionadas mediante `portfolio_id` y su última valoración. Sin parámetro se usa la demo I1 |
| `POST` | `/api/portfolio/refresh-prices` | Guardar una valoración de la cartera indicada por `portfolio_id`. La API también admite `mode=simulated` y `mode=live` explícitos |
| `GET`, `PUT` | `/api/profile` | Leer / crear versión de perfil |
| `POST` | `/api/analyses` | Encolar análisis de prueba con `portfolio_id`, `portfolio_version` y `valuation_id`. Una petición sin cuerpo conserva el recorrido histórico I0 |
| `GET` | `/api/analyses/{id}` | Estado, error, informe generado |
| `GET` | `/api/reports` | Listado de informes |
| `GET` | `/api/reports/{id}` | Informe y snapshot inmutable completo |

## Posiciones y datos simulados

El módulo `app.portfolio` representa instrumentos, listings, cuentas y posiciones. Las observaciones de NAV, cierre, último precio, precio indicativo y FX tienen procedencia propia. El contrato interno usa fechas ISO para NAV y `Decimal` para cantidades, precios, tasas y coberturas. En JSON, las cantidades fraccionarias se transmiten como cadenas. La tasa FX expresa unidades de la moneda cotizada por cada unidad de moneda base.

`app.portfolio.fixtures` contiene una cartera con identificadores de instrumentos reales y cantidades, precios, fechas y tasas inventados. `FixtureMarketDataProvider` devuelve observaciones simuladas por instrumento y listing exactos. E01 con plaza desconocida conserva `listing_id=None` y la búsqueda queda sin cotización. F04 ejemplifica un precio ausente, y una composición de peso desconocido se representa con `None`.

```bash
python -m pytest -q tests/test_portfolio_models.py
```

## I1.3 · Valoración determinista offline

`value_portfolio()` recibe el snapshot de tenencias, el catálogo y las observaciones fijadas por el llamador. El resultado conserva la versión de cartera, las posiciones, los importes en divisa de cotización y divisa base, y las observaciones de precio y FX empleadas. Se identifica con el `snapshot_id` que proporciona el llamador.

- Los fondos tradicionales usan NAV de su clase. Las acciones, ETF y ETC requieren un listing explícito y un cierre por defecto. Se puede seleccionar `LAST` al invocar el motor. El fixture de Bitcoin usa un precio indicativo. Los bonos individuales quedan sin valoración hasta disponer de un método para el nominal y el tipo de cotización.
- El motor usa `Decimal` con 38 cifras de precisión y redondeo al par. El redondeo a unidades monetarias menores corresponde a la presentación. Con EUR como base y una tasa de 1,10 USD por EUR, se dividen los USD entre 1,10. Se admite el par inverso mediante multiplicación. La tasa debe corresponder a la fecha del precio.
- La antigüedad máxima del precio se configura en días naturales y por defecto exige la fecha de valoración. El motor descarta observaciones posteriores al corte UTC. La cobertura se mide por número de posiciones valoradas.
- `COMPLETE` incluye el total. `PARTIAL` y `MISSING` conservan `total_value=None` y el valor conocido. El motivo por posición permite distinguir falta de precio, FX ausente, plaza ambigua y otros problemas.
- `ValuationSnapshotStore` guarda y recupera los documentos en SQLite local. Guardar el mismo documento es idempotente. Un intento de reutilizar su ID con otro contenido falla.

```bash
python -m pytest -q tests/test_portfolio_valuation.py
```

## Cargar carteras ficticias desde el dashboard

1. Descarga el CSV UTF-8 de *Holdings* con símbolo, plaza y cantidad. En **Importar cartera → Desde archivo**, elige un nombre para la cuenta ficticia, adjunta el archivo y pulsa **Vista previa**. [Exportación de cartera](https://www.investing-support.com/hc/en-us/articles/360000249657-How-to-Download-Your-Portfolio-from-Investing-com).
2. Revisa las posiciones y pulsa **Importar**. El resumen aporta una posición agregada por instrumento y plaza. El desglose de posiciones abiertas aporta los lotes cuando está disponible. La app guarda y activa la cartera y su valoración en una operación, con cero consultas de mercado y cero análisis encolados.
3. Pulsa **Analizar cartera** con el worker en marcha. El informe de prueba conserva la cartera, su versión, la valoración, el perfil y los documentos fijados al encolar. El selector de informes también permite abrir los históricos de I0.

El mismo nombre identifica la cuenta. Repetir un archivo idéntico conserva la versión y la valoración. Una exportación distinta sustituye el conjunto activo y conserva el anterior en SQLite. **Conectar cuenta** muestra Alpaca Paper como pendiente mientras se completa la validación OAuth externa.

La valoración distingue los importes y pesos declarados por Investing.com de los que calcula I1. El total declarado en EUR se muestra aunque falte FX por posición y el total calculado siga indeterminado. La fecha de referencia procede de una columna explícita o del nombre del archivo, con el origen indicado. La fecha de apertura, la hora de cotización y el instante UTC de carga se conservan por separado. Para probar el consumidor determinista se incluye un [ejemplo de entrada y salida](docs/ejemplos/analisis_cartera_importada_demo.json).

### Aceptación del recorrido

La [suite de aceptación](tests/test_investing_acceptance.py) se ejecuta con `python -m pytest -q`. El [acta de cierre](docs/historico/cartera/CIERRE_DEMO_INVESTING.md#evidencia-de-aceptación) recoge los resultados y los identificadores de cartera, valoración, trabajo e informe de la ejecución en Chrome.

## I1.4 · Refresco de precios en el dashboard

Al abrir el dashboard por primera vez, **Cartera** comienza vacía si aún no hay una importación. La cartera ficticia original está disponible en el selector. La API devuelve `portfolio`, `valuation`, `valuation_mode` (`imported`, `simulated` o `live`) y los datos del CSV en `imported` cuando proceden. Cada refresco correcto guarda una valoración con identidad propia. **Ver valoración del CSV** permite volver a consultar o analizar la valoración original después de un refresco.

El análisis multiactivo usa [`PortfolioAnalysisView v1`](docs/cartera/CONTRATO_CARTERA_ANALISIS_V1.md) en un contexto de prueba versionado. El consumidor es determinista y se ejecuta en el mismo worker. El contrato de inteligencia v1.1 sigue disponible para I0.

### Datos de mercado

En un entorno autorizado para consultar, conservar y mostrar los datos, configura `ENABLE_LIVE_MARKET_DATA=1` y `EODHD_API_TOKEN` en el entorno del proceso API. Con Docker Compose puedes copiarlas desde `.env.example` a un archivo local `.env` ignorado por Git y recrear el servicio API con `docker compose up -d --build api`. Para Uvicorn local, exporta las variables antes de arrancar. **Actualizar precios** solicita el modo de mercado (`live`). Mercado deshabilitado o sin credencial devuelve HTTP 503. Una credencial rechazada por EODHD devuelve HTTP 502. El modo simulado sigue disponible por API mediante `?mode=simulated`.

La valoración de mercado toma la fecha UTC del inicio del refresco. Se usa el último NAV de la clase o cierre diario sin ajustar del listing exacto dentro de los últimos siete días naturales. La fecha efectiva de cada precio se muestra junto a su fuente y puede ser anterior a la fecha de valoración. Para convertir USD a EUR se usa la tasa del BCE de la misma fecha que el precio. El importe conocido suma las posiciones valoradas. Las filas sin datos válidos conservan su motivo y el total queda indeterminado. La pantalla recupera de SQLite la fecha y el modo guardados de la valoración.

Cada refresco de mercado consulta una vez por símbolo resuelto y solicita FX por combinación necesaria de moneda y fecha. La cobertura parcial deja las filas afectadas con `MISSING_PRICE` o `MISSING_FX`. Si el refresco de una cartera importada se queda sin precios utilizables, la API devuelve HTTP 502 y conserva la valoración previa. Consulta el [ADR de proveedor](docs/adr/0001-market-data-provider.md) antes de compartir el acceso o el volumen.

Para Bitcoin, EODHD publica el par `BTC-EUR.CC`. Se usa como precio indicativo en EUR el cierre de su última barra diaria completa, con corte al día anterior en UTC. [Catálogo de criptomonedas de EODHD](https://eodhd.com/financial-apis/list-supported-crypto-currencies).

```bash
python -m pytest -q tests/test_portfolio_refresh.py tests/test_portfolio_market_refresh.py
```
