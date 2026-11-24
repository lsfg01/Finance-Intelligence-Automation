# Análisis de inversiones — incremento 0.1

**Demo local con tenencias y noticias ficticias.** Funciona offline por defecto con precios e inteligencia simulados. El refresco de mercado opcional consulta EODHD y el BCE bajo demanda. El worker puede usar un modelo local con Ollama.

Consulta el [acta de cierre de I1](docs/CIERRE_I1_CARTERA_Y_PRECIOS.md) para el alcance de la entrega y las comprobaciones realizadas.

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

- Una cartera y un perfil ficticios, editables por API; cada edición crea una nueva versión.
- Composiciones de ETF con fuente y fecha y con parte conocida/incompleta.
- Endpoint `POST /api/analyses` que **encola** un trabajo. Ningún análisis se ejecuta sin acción explícita.
- Worker independiente que procesa solo trabajos encolados, con estado consultable.
- Cálculo de exposición directa/indirecta exacto con `Decimal`, sin mezclar divisas sin FX.
- Informe persistido e inmutable ligado a versión de cartera, perfil y snapshot documental.
- Dashboard de solo lectura con un botón de análisis y advertencias de simulación.

## Limitaciones deliberadas de este incremento

No hay todavía importador CSV, chat, autorización de usuarios, exportación de informes, búsqueda histórica/RAG, alertas, métricas de costes o despliegue público. La cola SQLite es solo para un worker local en demostración. La API de I0 permite crear versiones de la cartera y del perfil. Los informes son para revisión humana.

El worker incorpora el resultado de inteligencia al informe, en `result.intelligence`, sin alterar las exposiciones deterministas. Por defecto utiliza el mock; el modelo local Ollama es opcional y solo acepta datos de demostración. Véanse [uso de inteligencia](docs/USO_INTELIGENCIA.md) y [contrato propuesto](docs/CONTRATO_DATOS_UNIFICADO.md).

**No exponer esta demo directamente a Internet:** los endpoints de escritura no tienen autenticación.

## API

| Método | Ruta | Efecto |
|---|---|---|
| `GET` | `/api/health` | Estado y modo de ejecución |
| `GET`, `PUT` | `/api/portfolio` | Leer / crear versión de cartera |
| `GET` | `/api/portfolio/valuation` | Leer las tenencias multiactivo activas y su última valoración guardada |
| `POST` | `/api/portfolio/refresh-prices` | Guardar una valoración a demanda. El modo automático usa la configuración del servidor. La API también admite `mode=simulated` y `mode=live` explícitos |
| `GET`, `PUT` | `/api/profile` | Leer / crear versión de perfil |
| `POST` | `/api/analyses` | Encolar nuevo análisis manual |
| `GET` | `/api/analyses/{id}` | Estado, error, informe generado |
| `GET` | `/api/reports` | Listado de informes |
| `GET` | `/api/reports/{id}` | Informe y snapshot inmutable completo |

## Organización

```text
backend/app/{models,fixtures,analysis,db,main,worker}.py
backend/app/portfolio/{models,fixtures,valuation,valuation_store}.py
frontend/index.html
tests/test_analysis.py, tests/test_api.py, tests/test_portfolio_models.py
docs/PLAN_ARQUITECTURA.md, docs/DECISIONES_PENDIENTES.md
```

Consultar `docs/PLAN_ARQUITECTURA.md` para evolución de etapa 1 y decisiones de producción.

## I1.1 · Cartera multiactivo offline

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

## I1.4 · Refresco de precios en el dashboard

Al abrir el dashboard, **Cartera** muestra las once posiciones y sus cantidades ficticias. La API devuelve el snapshot de tenencias como `portfolio`, la última `valuation` del mismo identificador, versión y snapshot, y su `valuation_mode` (`simulated` o `live`). Si todavía no hay una valoración guardada, la pantalla muestra los precios pendientes. Cada refresco correcto devuelve HTTP 201 y crea un snapshot propio. La demo simulada muestra diez de once posiciones valoradas, el valor conocido y el total indeterminado.

La cartera multiactivo se inicializa una vez por versión en el mismo SQLite, incluso si el volumen contiene la demo I0. **Analizar cartera** usa el snapshot de I0 fijado al encolar y añade el resultado de inteligencia al informe. La conexión con la cartera multiactivo queda pendiente de coordinación mediante [`PortfolioAnalysisView v1`](docs/CONTRATO_CARTERA_ANALISIS_V1.md).

### Datos de mercado

En un entorno autorizado para consultar, conservar y mostrar los datos, configura `ENABLE_LIVE_MARKET_DATA=1` y `EODHD_API_TOKEN` en el entorno del proceso API. Con Docker Compose puedes copiarlas desde `.env.example` a un archivo local `.env` ignorado por Git y recrear el servicio API con `docker compose up -d --build api`. Para Uvicorn local, exporta las variables antes de arrancar. Pulsa **Actualizar precios** para ejecutar el modo configurado en el servidor. Con mercado habilitado, una credencial ausente devuelve HTTP 503 y una credencial rechazada por EODHD devuelve HTTP 502. El modo simulado sigue disponible cuando el servidor funciona offline o mediante `?mode=simulated`.

La valoración de mercado toma la fecha UTC del inicio del refresco. Se usa el último NAV de la clase o cierre diario sin ajustar del listing exacto dentro de los últimos siete días naturales. La fecha efectiva de cada precio se muestra junto a su fuente y puede ser anterior a la fecha de valoración. Para convertir USD a EUR se usa la tasa del BCE de la misma fecha que el precio. El importe conocido suma las posiciones valoradas. Las filas sin datos válidos conservan su motivo y el total queda indeterminado. La pantalla recupera de SQLite la fecha y el modo guardados de la valoración.

Cada refresco de mercado consulta una vez por símbolo resuelto y solicita FX por combinación necesaria de moneda y fecha. Los fallos de proveedor dejan la fila sin observación, con `MISSING_PRICE` o `MISSING_FX` según corresponda. El modo de mercado conserva sus snapshots en el volumen local. Consulta el [ADR de proveedor](docs/adr/0001-market-data-provider.md) antes de compartir el acceso o el volumen.

Para Bitcoin, EODHD publica el par `BTC-EUR.CC`. Se usa como precio indicativo en EUR el cierre de su última barra diaria completa, con corte al día anterior en UTC. [Catálogo de criptomonedas de EODHD](https://eodhd.com/financial-apis/list-supported-crypto-currencies).

```bash
python -m pytest -q tests/test_portfolio_refresh.py tests/test_portfolio_market_refresh.py
```
