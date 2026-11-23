# Análisis de inversiones — incremento 0.1

**Demo local con tenencias y noticias ficticias.** Funciona offline por defecto. El modo de mercado opcional consulta precios diarios de EODHD y tipos de cambio de referencia del BCE bajo demanda.

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

No hay todavía importador CSV, motor LLM, chat, autorización de usuarios, exportación de informes, búsqueda histórica/RAG, alertas, métricas de costes o despliegue público. La cola SQLite es solo para un worker local en demostración: antes de servir múltiples usuarios se necesita una infraestructura transaccional adecuada, control de acceso, migraciones y auditoría ampliada. La interfaz demuestra la lectura, no la edición del perfil/cartera, aunque la API de I0 permite nuevas versiones.

**No exponer esta demo directamente a Internet:** los endpoints de escritura no tienen autenticación.

## API

| Método | Ruta | Efecto |
|---|---|---|
| `GET` | `/api/health` | Estado y modo de ejecución |
| `GET`, `PUT` | `/api/portfolio` | Leer / crear versión de cartera |
| `GET` | `/api/portfolio/valuation` | Leer las tenencias multiactivo activas y su última valoración guardada |
| `POST` | `/api/portfolio/refresh-prices` | Guardar una valoración de la cartera activa a demanda con `mode=simulated` o `mode=live` |
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

Al abrir el dashboard, **Cartera** muestra las once posiciones y sus cantidades ficticias. La API devuelve el snapshot de tenencias como `portfolio` y la última `valuation` del mismo identificador, versión y snapshot. Antes de pulsar **Actualizar precios**, la valoración puede ser `null` y los precios aparecen como pendientes. Cada refresco simulado devuelve HTTP 201 y crea un snapshot propio. La demo muestra diez de once posiciones valoradas, el valor conocido y el total indeterminado.

La cartera multiactivo se inicializa una vez por versión en el mismo SQLite, incluso si el volumen contiene la demo I0. **Analizar cartera** usa la cartera versionada del prototipo y sigue siendo una acción independiente. Los informes guardados conservan el snapshot con el que se crearon.

### Datos de mercado

En un entorno autorizado para consultar, conservar y mostrar los datos, configura `ENABLE_LIVE_MARKET_DATA=1` y `EODHD_API_TOKEN` en el entorno del proceso API. Con Docker Compose puedes usar un archivo local `.env` ignorado por Git. Para Uvicorn local, exporta las variables antes de arrancar. Elige **Datos de mercado** y pulsa **Actualizar precios**. Si falta la habilitación o la credencial, el servidor devuelve HTTP 503.

Se usa el NAV de la clase o el cierre diario sin ajustar del listing exacto, con hasta siete días naturales de antigüedad. La fecha efectiva de cada precio se muestra junto a su fuente. Para convertir USD a EUR se usa la tasa del BCE de la misma fecha que el precio. El importe conocido suma las posiciones valoradas. Las filas sin datos válidos conservan su motivo y el total queda indeterminado. Las observaciones de mercado se distinguen de las simuladas por observación, mientras que `valuation.is_simulated` sigue reflejando las tenencias ficticias.

Cada refresco de mercado consulta una vez por símbolo resuelto y solicita FX por combinación necesaria de moneda y fecha. Los fallos de proveedor dejan la fila sin observación, con `MISSING_PRICE` o `MISSING_FX` según corresponda. El modo de mercado conserva sus snapshots en el volumen local. Consulta el [ADR de proveedor](docs/adr/0001-market-data-provider.md) antes de compartir el acceso o el volumen.

```bash
python -m pytest -q tests/test_portfolio_refresh.py tests/test_portfolio_market_refresh.py
```
