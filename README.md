# Análisis de inversiones — incremento 0.1

**Demo funcional OFFLINE con datos 100 % inventados.** Ninguna API de bróker, proveedor de precios, crawler o modelo de IA está conectada. No ejecuta operaciones ni formula recomendaciones utilizables en mercados reales.

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

No hay todavía conexión a fuentes reales, importador CSV, motor LLM, chat, autorización, estimación de FX, exportación de informes, búsqueda histórica/RAG, alertas, métricas de costes o despliegue público. La cola SQLite es solo para un worker local en demostración: antes de servir múltiples usuarios se necesita una infraestructura transaccional adecuada, control de acceso, migraciones y auditoría ampliada. La interfaz demuestra la lectura, no la edición del perfil/cartera, aunque la API permite nuevas versiones.

**No exponer esta demo directamente a Internet:** los endpoints de escritura no tienen autenticación.

## API

| Método | Ruta | Efecto |
|---|---|---|
| `GET` | `/api/health` | Estado y modo de ejecución |
| `GET`, `PUT` | `/api/portfolio` | Leer / crear versión de cartera |
| `GET`, `PUT` | `/api/profile` | Leer / crear versión de perfil |
| `POST` | `/api/analyses` | Encolar nuevo análisis manual |
| `GET` | `/api/analyses/{id}` | Estado, error, informe generado |
| `GET` | `/api/reports` | Listado de informes |
| `GET` | `/api/reports/{id}` | Informe y snapshot inmutable completo |

## Organización

```text
backend/app/{models,fixtures,analysis,db,main,worker}.py
backend/app/portfolio/{models,fixtures}.py
frontend/index.html
tests/test_analysis.py, tests/test_api.py, tests/test_portfolio_models.py
docs/PLAN_ARQUITECTURA.md, docs/DECISIONES_PENDIENTES.md
```

Consultar `docs/PLAN_ARQUITECTURA.md` para evolución de etapa 1 y decisiones de producción.

## I1.1 · Cartera multiactivo offline

El módulo `app.portfolio` representa instrumentos, listings, cuentas y posiciones. Las observaciones de NAV, cierre, último precio, precio indicativo y FX tienen procedencia propia. El contrato interno usa fechas ISO para NAV y `Decimal` para cantidades, precios, tasas y coberturas. En JSON, las cantidades fraccionarias se transmiten como cadenas. La tasa FX expresa unidades de la moneda cotizada por cada unidad de moneda base.

`app.portfolio.fixtures` contiene una cartera con identificadores de instrumentos reales y cantidades, precios, fechas y tasas inventados. `FixtureMarketDataProvider` devuelve observaciones simuladas por instrumento y listing exactos. E01 con plaza desconocida conserva `listing_id=None` y la búsqueda queda sin cotización. F04 ejemplifica un precio ausente, y una composición de peso desconocido se representa con `None`. La integración con la API y el cálculo de valoraciones corresponden a incrementos posteriores.

```bash
python -m pytest -q tests/test_portfolio_models.py
```
