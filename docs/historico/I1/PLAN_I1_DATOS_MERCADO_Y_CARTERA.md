# I1 — Validación de datos de mercado y cartera multiactivo

**Proyecto:** Automatización de análisis de inversiones\
**Estado:** Propuesta técnica para aprobación; NO implementada\
**Revisión:** 2026-11-22\
**Responsable:** módulo portfolio / datos de mercado\
**Base consultada:** especificación inicial del proyecto, MVP v0.1.1 y `AGENTS.md` v1.0

## 0. Resumen ejecutivo y decisión propuesta

El primer incremento debe validar que es viable **identificar y valorar** una cartera ficticia compuesta por clases de activos diversas, incluyendo **fondos indexados tradicionales europeos**, antes de comprometer una integración con brókeres.

**No se presupone acceso a precios, NAV ni holdings de ningún producto concreto.** La documentación comercial de una API demuestra una capacidad anunciada, **no** la cobertura de un ISIN determinado, de una clase de participación concreta ni los derechos de reutilización.

Decisión recomendada:

1. **Prueba de datos (spike) antes de fijar proveedor:** EODHD como candidato prioritario; Twelve Data como contraste técnicamente válido pero posiblemente costoso para NAV de fondos europeos.
2. Adoptar ya **modelo interno multiactivo** con instrumentos, posibles mercados/listings, posiciones, observaciones de precio/NAV, divisas, snapshots y procedencia separados.
3. Incluir fondos indexados de renta variable **y** renta fija en la cartera ficticia, con cantidades inventadas y productos reales identificados.
4. Primer flujo de usuario: **crear cartera ficticia → resolver identidades → actualizar cotizaciones/NAV a demanda → calcular valoración parcial o completa → guardar snapshot → mostrar fechas y errores**.
5. Mantener análisis de noticias/agentes, brókeres, streaming, rentabilidades avanzadas e importación de extractos fuera del incremento.

### Alcance vs expectativas

- **Sí desde I1:** categorías multiactivo; cartera ficticia; tres fondos tradicionales en la batería de validación; distinción NAV/último cierre/precio cotizado; FX; actualización manual; fechas, procedencia y estado de cobertura.
- **No garantizado desde I1:** cotización real para todos los instrumentos, datos intradía para fondos, composiciones completas de cualquier fondo o precios de bonos individuales. Los instrumentos no cubiertos deben mostrarse con estado **SIN_VALORACION** en vez de un número inventado.
- **No en I1:** conexión con MyInvestor/Trade Republic, permisos de usuario, operaciones, decisiones de inversión, streaming, RAG y agentes.

## 1. Investigación de proveedores (documentación oficial)

| Fuente | Capacidades anunciadas relevantes | Obstáculo o comprobación pendiente | Decisión I1 |
|---|---|---|---|
| **EODHD** | Búsqueda por ISIN; EOD de acciones/ETF/fondos; exchange virtual `EUFUND` para fondos europeos; fundamentales y holdings de ciertos instrumentos. | Verificar cada ISIN en `EUFUND` y su NAV/fecha/divisa; planes y permisos para uso por un equipo. El anuncio antiguo de `EUFUND` no demuestra cobertura actual de la lista. | **Candidato A, prueba primero.** |
| **Twelve Data** | ETF, acciones y fondos; anuncia históricos NAV, composición, referencia por ISIN. | ISIN como add-on; precio de NAV de fondos en **Pro**; métricas de mutual funds en **Ultra** según página de precios de noviembre 2026. Verificar cobertura por clase y presupuesto. | **Candidato B, benchmark y contraste.** |
| **FMP** | ETF/fund metadata, holdings y disclosures. | Alcance de fondos europeos y funciones de holdings varía por plan (la página anuncia coberturas amplias en Ultimate). No escogerlo para NAV sin evidencia adicional. | Investigación opcional P1. |
| **Alpha Vantage** | Acciones, ETF, FX, búsqueda y perfil ETF. | Plan gratuito limitado; sin evidencia suficiente de NAV para todos los fondos indexados europeos de prueba. | Alternativa secundaria, no bloqueante. |
| **CNMV** | XML de información individual sobre IIC españolas; valor liquidativo básico mensual y composición trimestral. | **No** es un feed NAV diario general de fondos domiciliados en Irlanda/Luxemburgo. Comprobar cobertura de un fondo español de control. | Fuente pública de contraste/enriquecimiento. |
| **OpenFIGI** | Mapeo de identificadores financieros, incluidos ISIN. | No suministra precios; un ISIN puede tener múltiples listings; respuesta no sustituye verificación humana. | Complemento de resolución, no proveedor de precios. |
| **BCE / ECB** | API de tipos de cambio de referencia diarios. | No son tasas de ejecución ni intradía; hay festivos y retrasos. | Fuente de FX de referencia para valoración EOD. |
| **CoinGecko** | Cotización cripto con IDs de activo, por ejemplo `bitcoin`. | Cobertura/licencia y límites de cuenta demo; no usar tickers cripto ambiguos como identificadores únicos. | Complemento para BTC, optativo en primera demo conectada. |
| **Gestoras (Vanguard/iShares/Fidelity)** | Fichas oficiales de clase, NAV publicado y, en algunos ETF, holdings descargables. | Disponibilidad de **API automatizable** y términos de reutilización por verificar; no presumir que la página pública permite scraping. | **Fuente de verificación manual**, y holdings solo si existe acceso autorizado. |

**Detalles económicos relevantes, verificados en páginas de planes el 22-11-2026:**

- EODHD anuncia *EOD Historical Data All-World* alrededor de **19,99 USD/mes**, *Fundamentals* alrededor de **59,99 USD/mes** y un nivel gratuito limitado. Precio promocional o plan personal no implica derechos de uso compartido/comercial.
- Twelve Data anuncia **Pro** alrededor de **229 USD/mes** (NAV de fondos) y **Ultra** alrededor de **999 USD/mes** (métricas avanzadas de fondos). Sus planes pueden cambiar; presupuesto definitivo sujeto a contratación y derechos.
- CoinGecko publica un plan Demo gratuito con límite mensual; OpenFIGI permite llamadas gratuitas con límites y el BCE publica su API de series.

**Alerta de licencia:** EODHD señala expresamente que el uso por varias personas, para clientes o con redistribución puede considerarse comercial. Twelve Data limita el uso y redistribución según plan. Solicitar aclaración por escrito antes de compartir una misma suscripción/dataset entre los dos desarrolladores. El repositorio NO alojará respuestas reales licenciadas, claves, carteras personales ni volcados de mercado.

### Fuentes oficiales para la revisión

- EODHD — búsqueda/ISIN: https://eodhd.com/financial-apis/search-api-for-stocks-etfs-mutual-funds
- EODHD — `EUFUND`: https://eodhd.com/financial-apis-blog/new-european-funds-data
- EODHD — históricos: https://eodhd.com/financial-apis/api-for-historical-data-and-volumes
- EODHD — precios: https://eodhd.com/pricing
- EODHD — licencia: https://eodhd.com/help/commercial
- Twelve Data — fondos: https://twelvedata.com/docs/mutual-funds/mf-performance
- Twelve Data — precios: https://twelvedata.com/pricing
- Twelve Data — add-on ISIN: https://support.twelvedata.com/en/articles/11132744-how-to-request-access-to-isins
- Twelve Data — términos: https://twelvedata.com/terms
- FMP — ETF/fondos: https://site.financialmodelingprep.com/developer/docs/stable/holdings
- CNMV — descargas IIC: https://www.cnmv.es/portal/publicaciones/descarga-informacion-individual?lang=es
- OpenFIGI — API: https://www.openfigi.com/api/documentation
- ECB — API y series EXR: https://data.ecb.europa.eu/help/api/data
- CoinGecko — documentación/API: https://www.coingecko.com/en/api

## 2. Batería de instrumentos para evaluar cobertura

Los ISIN de la tabla se han corroborado con fichas de emisores/mercados. **No se han confirmado cotizaciones reales de estos ISIN en EODHD ni Twelve Data.** No usar estos productos como recomendación de inversión; son casos de integración.

| ID | Tipo | Instrumento / clase exacta | Identificador de referencia | Función de prueba | Fuente de identidad |
|---|---|---|---|---|---|
| F01 | Fondo indexado, acciones | Vanguard Global Stock Index Fund **EUR Acc** | `IE00B03HD191` | NAV diario, clase EUR, fondo no cotizado | Vanguard |
| F02 | Fondo indexado, acciones | Fidelity MSCI World Index Fund **P-ACC-EUR** | `IE00BYX5NX33` | Validar otra gestora, clase EUR; no confundir con clase hedged | Fidelity |
| F03 | Fondo indexado, bonos | Vanguard Global Bond Index Fund **EUR Hedged Acc** | `IE00B18GC888` | NAV de renta fija y clase cubierta | Vanguard |
| E01 | ETF acciones | iShares Core MSCI World UCITS ETF Acc | `IE00B4L5Y983` | Listing **EUNL / Xetra / EUR** vs **IWDA / LSE / USD**; mismo ISIN, cotizaciones distintas | iShares |
| E02 | ETF acciones | Vanguard FTSE All-World UCITS ETF Acc | `IE00BK5BQT80` | ETF UCITS y selección de plaza/moneda | Vanguard |
| E03 | ETF bonos | iShares Core Global Aggregate Bond UCITS ETF **EUR Hedged Acc** | `IE00BDBRDM35` | ETF bonos, distinguir precio de mercado y NAV del ETF | iShares |
| A01 | Acción EUR | Iberdrola SA | `ES0144580Y14` | Mercado español y cotización EUR | BME |
| A02 | Acción USD | Microsoft Corp. | `US5949181045` | Cotización USD + conversión con FX de referencia | Microsoft |
| C01 | ETC oro | iShares Physical Gold ETC | `IE00B4ND3602` | **ETC, no ETF**; mercado/moneda a resolver | iShares |
| K01 | Criptomoneda | Bitcoin | CoinGecko ID: `bitcoin` | Sin ISIN; valoración en EUR; timestamp diferente | CoinGecko |
| F04* | Fondo español, no indexado | MyInvestor Cartera Permanente | `ES0156572002` | Caso límite CNMV / cobertura de fondo español | MyInvestor |
| FX01 | Divisa | EUR/USD | Serie ECB: `EXR.D.USD.EUR.SP00` | Convertir USD a EUR sin invertir mal el tipo | BCE |

`F04` es caso ampliado, no bloquea que tres fondos indexados estén cubiertos. Para `E02`, `E03` y `C01` no se fija un ticker/venue hasta resolverlo en la prueba; inventar un código de proveedor es un error de identificación.

**Referencias primarias:**

- Vanguard F01: https://www.vanguard.co.uk/professional/product/mf/equity/9837/global-stock-index-fund-eur-acc
- Fidelity F02: https://www.fidelityinternational.com/FILPS/Documents/en/current/pro.en.xx.IE00BYX5NX33.pdf
- Vanguard F03: https://www.vanguard.co.uk/professional/product/fund/bond/9197/global-bond-index-fund-eur-hedged-acc
- iShares E01: https://www.ishares.com/uk/individual/en/products/251882/ishares-core-msci-world-ucits-etf-swda
- Vanguard E02: https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-accumulating-Vanguard
- iShares E03: https://www.ishares.com/uk/individual/en/products/291770/ishares-core-global-aggregate-bond-ucits-etf-aggh-hedged
- BME A01: https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/ficha.iberdrola-es0144580y14.html
- Microsoft A02: https://www.microsoft.com/en-us/investor/FAQ
- iShares C01: https://www.ishares.com/uk/individual/en/products/258441/ishares-physical-gold-etc-sgln
- MyInvestor F04: https://myinvestor.es/inversion/fondos-inversion/myinvestor-cartera-permanente/

**Regla:** la identidad del instrumento es su clase/serie; no equiparar el fondo con todas sus share classes. Un ETF puede tener el mismo ISIN en varias bolsas con ticker, divisa y precio distintos. La divisa base del fondo tampoco tiene por qué ser la divisa de cotización de la participación.

## 3. Spike de proveedor, antes de codificar la aplicación

### 3.1. Qué debe comprobarse en cada fila

Guardar una [matriz de evidencia](RESULTADOS_SPIKE_I1.md) con al menos:

- Proveedor, plan/entorno y fecha de prueba (sin anotar el token).
- Identificador consultado: ISIN o ID externo, símbolo resuelto, bolsa/MIC y moneda de listado.
- Resolución inequívoca de la **misma clase** de instrumento (`PASS`, `AMBIGUOUS`, `NOT_FOUND`, `PLAN_BLOCKED`).
- Si hay observación: valor, moneda, **tipo** (`NAV`, `EOD_CLOSE`, `LAST`, `INDICATIVE`), `price_as_of`, `retrieved_at` y retraso.
- Valoración de frescura considerando días hábiles bursátiles, NAV y hora de publicación.
- Comparación con referencia independiente del emisor **de la misma fecha y divisa**; documentar diferencias y supuestos, no aplicar tolerancia universal a mercados distintos.
- Coste por llamada, límites, errores HTTP y condiciones de uso.
- Disponibilidad de composiciones de fondos/ETF (sí/no/parcial, fecha y alcance), solo **informativa** para fases posteriores.

### 3.2. Secuencia de verificación y decisión

1. **EODHD gratuito:** buscar cada ISIN, consultar catálogo `EUFUND` y solicitar una serie EOD cuando el plan lo permita. `demo` prueba algunos símbolos estadounidenses, no garantiza fondos europeos. Validar especialmente F01–F03.
2. **Twelve Data:** documentar si el nivel actual permite localizar y valorar cada ISIN; registrar bloqueo por `ISIN add-on`, `Pro` o `Ultra`. No contratar un plan caro sin cobertura confirmada por soporte.
3. **Referencia independiente:** contrastar fecha/moneda NAV con la web oficial de Vanguard/Fidelity; usar BCE para USD/EUR; documentar diferencias por cierre o mercado, no falsos errores.
4. **Gate:** si **no es posible recuperar valores verificables de F01–F03 con una opción permitida y asumible**, NO declarar selección de proveedor resuelta. Solicitar muestras/cobertura a proveedores y mantener esos instrumentos sin valor o con un **NAV manual explícito y auditado**, nunca inventado.
5. Decidir por ADR el proveedor principal y su alcance; el contrato interno sigue independiente de la decisión.

### 3.3. Matriz de puntuación (después de las pruebas)

- 35 %: **identificación y NAV de fondos europeos** exactos (prioridad F01–F03).
- 20 %: cobertura de acciones, ETF, ETC y otros instrumentos de la batería.
- 15 %: calidad de valoraciones (tipo de precio, timestamp, moneda y consistencia).
- 15 %: licencia, coste, límites y uso aceptado por el equipo.
- 10 %: facilidad de integración, soporte y documentación.
- 5 %: holdings/composiciones aprovechables más adelante.

**Criterio de descarte:** sin derechos claros de uso o sin identidad de share class, un proveedor no pasa a integración aunque tenga muchos símbolos. Registrar cobertura como `0/1` solo cuando se haya comprobado en API y guardar evidencias redaccionadas (sin payloads licenciados en Git).

## 4. Arquitectura acordable del módulo Portfolio

### 4.1. Capas propuestas

```text
Entradas ficticias/manuales                     APIs financieras autorizadas
          |                                          |
          v                                          v
    PortfolioImporter                     InstrumentResolver / MarketDataProvider
          |                                          |
          +---------------+--------------------------+
                          v
                 MODELO DE DOMINIO
       Instrument, Listing, Position, Quote, FX, Snapshot
                          |
                          v
                 ValuationService
       Decimal + conversión FX + estado de cobertura
                          |
                   +------+------+
                   v             v
             Persistencia      API interna
                   |             |
                   +-------+-----+
                           v
                  Dashboard / Analizador IA
```

### 4.2. Entidades (contratos **propuestos**, no implementados)

- `Instrument`: `instrument_id` interno estable; `asset_type` extensible; nombre, ISIN **opcional**, identificador de emisión/clase y divisa de participación cuando aplique. `issuer_id` **diferente** de `instrument_id`.
- `Listing`: `listing_id`; `instrument_id`; bolsa/MIC; ticker local; divisa cotizada. Relación 1:N con Instrument.
- `ProviderSymbol`: `provider`; `provider_symbol`; `listing_id` o `instrument_id`; fecha de comprobación y estado de resolución. **Nunca** derivar códigos propietarios suponiendo que ISIN=ticker.
- `Account` / `Portfolio`: cuenta lógica/ficticia, moneda base, entradas normalizadas.
- `Position`: `instrument_id`, `account_id`, cantidad `Decimal`, `as_of`. **Sin precio dentro de Position**: el mercado cambia sin que cambie la tenencia.
- `MarketObservation`: `instrument_id` + `listing_id?`; `value Decimal`; `currency`; `price_type`; `price_as_of` como **fecha NAV** o timestamp de sesión, según el tipo; `retrieved_at` UTC; proveedor, licencia, estado y `is_simulated`.
- `FXObservation`: par, tasa, fecha, origen, convención (`USD por 1 EUR`), timestamp. No invertir conversiones por intuición.
- `PortfolioSnapshot`: cantidades + referencias de cartera/versiones inmutables.
- `ValuationSnapshot`: `portfolio_snapshot_id`; IDs de precios/FX utilizados, valor total si completo, valor conocido si parcial, cobertura y warnings, fecha de cálculo.
- `FundComposition`: **contrato reservado**, con fecha, fuente y porcentaje de composición conocido. Su ingesta real no bloquea I1.

`price_as_of` puede ser una fecha sin hora para un NAV: no inventar `00:00:00Z` como hora de negociación. Distinguir: `share_class_currency`, `fund_base_currency`, `listing_currency`, `quote_currency` y `portfolio_currency`. Un precio de EUNL en EUR no debe convertirse de nuevo desde USD porque el fondo tenga divisa base USD.

**Clases mínimas de activo (modelo):** `EQUITY`, `ETF`, `MUTUAL_FUND`, `BOND`, `ETC_ETN`, `CRYPTO`, `CASH`, `OTHER`. El motor de valoración debe aplicar semántica por producto (ej. bonos cotizados en porcentaje de nominal no son automáticamente 1 unidad × precio). `OTHER` permite registrar un producto no soportado sin inventar su valoración.

### 4.3. Interfaces de adaptadores sugeridas

```python
class InstrumentResolver(Protocol):
    def search(self, query: str) -> list[InstrumentCandidate]: ...

class MarketDataProvider(Protocol):
    def get_latest(self, request: MarketDataRequest) -> MarketDataResult: ...
    # Result incluye FOUND/NOT_FOUND/AMBIGUOUS/RATE_LIMITED/UNAUTHORIZED/ERROR

class FXProvider(Protocol):
    def get_rate(self, base: str, quote: str, as_of: date) -> FXResult: ...

class PortfolioValuationService(Protocol):
    def value(self, holdings: PortfolioSnapshot, quotes: list[MarketObservation],
              fx: list[FXObservation]) -> ValuationSnapshot: ...
```

No ubicar claves, SQL ni llamadas HTTP en `Position` ni en el módulo de inteligencia. Validar nombres y modelos concretos en una PR de contrato antes de escribir consumidores.

### 4.4. Regla de precios y valoración

- Fondos tradicionales: preferir **NAV de la clase exacta**; no aproximar con el índice o ETF similar.
- Acciones/ETF/ETC: identificar listing, plaza, divisa y elegir explícitamente `EOD_CLOSE`/`LAST`, nunca mezclar con NAV ETF sin etiquetarlo.
- Crypto: identificar activo por ID del proveedor, no por ticker ambiguo.
- FX: definir dirección de tasa y usar `Decimal`; si falta FX requerido, esa posición queda sin valoración en divisa base.
- Bonos individuales: declarar `valuation_method` específico y dejar sin valorar si falta nominal, tipo de cotización o precio autorizado.
- Si faltan precios, registrar **valor conocido y proporción sin valorar**. No mostrar total parcial como valor total de la cartera.
- Persistir todas las observaciones usadas y los metadatos de procedencia; no actualizar retroactivamente el informe de un análisis previo.

## 5. Backlog incremental: tareas aptas para PR y Codex

### I1.0 — Spike de APIs y legalidad (sin modificar aplicación)

**Archivos permitidos:** [Matriz de evidencia](RESULTADOS_SPIKE_I1.md) y scripts descartables en `scripts/spikes/` si aprobados. Los resultados privados quedan fuera del repositorio.

- Crear cuenta/clave de prueba por desarrollador, tras comprobar términos.
- Validar todos los instrumentos F01–FX01, registrando resultados y bloqueos reales.
- Comparar proveedor A/B; documentar costes y licencias.
- Entregar ADR `docs/adr/0001-market-data-provider.md` con decisión o estado BLOQUEADO.

**Aceptar cuando:** tabla de resultados completa, incluso los NOT_FOUND/PLAN_BLOCKED; no hay selección afirmada sin pruebas de NAV en F01–F03.

### I1.1 — Contrato multiactivo y fixtures offline

**Archivos recomendados:** nuevos `backend/app/portfolio/` y `tests/test_portfolio_models.py`. Cualquier cambio a `backend/app/models.py` es PR compartida.

- Tipos Pydantic, enums ampliables, `Decimal`, fechas y validadores.
- Cartera ficticia con cantidades y fechas inventadas, instrumentos referenciados por IDs reales.
- Provider `FixtureMarketDataProvider` con **precios completamente simulados**, etiquetados.
- Tests de ISIN ausente, 2 listings mismo ISIN, clase de fondo distinta, monedas y composiciones desconocidas.

**Aceptar cuando:** el modelo representa F01–FX01 sin asumir disponibilidad de cotización; tests offline sin Internet.

### I1.2 — Adaptadores de cotización y resolución

**Archivos:** `backend/app/market_data/`, `tests/test_market_data_*.py`; configuración con `.env.example` sin secretos.

- `EODHDProvider` (solo funciones verificadas) y `ECBFXProvider`; `TwelveDataProvider` solo si la prueba demuestra valor incremental.
- `InstrumentResolver` con mapeos explícitos, sin coincidencia por nombre automática ni codes de mercado inventados.
- Manejar timeout, HTTP 429, cuotas, retry con backoff y caché según frecuencia del instrumento.
- Mocks para tests; pruebas live opt-in, nunca obligatorias en CI.

**Aceptar cuando:** respuestas tipadas y errores visibles; ninguna clave en logs; implementación offline de referencia permanece funcional.

### I1.3 — Valoración determinista y snapshots

**Archivos:** `backend/app/portfolio/valuation.py` o equivalente; persistencia nueva bajo módulo propio; pruebas.

- Separa tenencias y precios; calcula valor en divisa de cotización y base.
- Funciona con fondos NAV, ETF EOD, acciones EUR/USD y posiciones sin precio.
- Snapshot inmutable con IDs de observaciones y versión de cartera.
- Pruebas de aritmética Decimal, dirección FX, datos stale, precio ausente, mismos ISIN en plazas distintas.

**Aceptar cuando:** resultados reproducibles dados los mismos inputs; total parcial claramente marcado.

### I1.4 — Integración mínima de API + dashboard (PR coordinada)

**Archivos compartidos:** `backend/app/main.py`, persistencia actual y `frontend/` tras revisión con el equipo.

- Endpoints tentativos: `GET /api/portfolio/valuation` y `POST /api/portfolio/refresh-prices` (contrato a validar; sin cambiar `/api/analyses`).
- Botón `Actualizar precios` distinto de `Analizar` y de `Sincronizar posiciones`.
- Mostrar instrument, cantidad, moneda, último valor, fecha NAV/cierre, origen, antigüedad y error parcial.
- Guardar snapshot, sin bloquear o sobreescribir informes anteriores.
- Test de arranque local/Docker, endpoints y flujo de refresco con fixture.

**Aceptar cuando:** un desarrollador nuevo puede levantar el proyecto y ejecutar un refresh simulado completo; un refresh real opt-in con claves locales devuelve resultados verificables o fallos honestos.

### I1.5 — Contrato de consumo para IA (PR coordinada con compañero)

- Diseñar `PortfolioAnalysisView v1` inmutable (cartera + valuation snapshot + cobertura + fechas + composición disponible).
- Los módulos de IA **no** consultan SQL ni proveedores ni modifican precios.
- Versionar contrato con ejemplos JSON y tests de compatibilidad. No sustituir `AnalysisContext` existente de la documentación sin revisión conjunta.

**Aceptar cuando:** el módulo de inteligencia consume un fixture del contrato sin requerir backend/BD/Internet; informes previos siguen ligados a su snapshot.

## 6. Colaboración Git y fronteras de cambio

- Rama `research/market-data-coverage` → I1.0; rama `feat/portfolio-domain` → I1.1; rama `feat/market-data-adapters` → I1.2; rama `feat/portfolio-valuation` → I1.3.
- Evitar tocar `backend/app/intelligence/`, su framework, prompts, RAG, evaluaciones o contratos sin aprobación.
- **No cambiar unilateralmente** `models.py`, `db.py`, `worker.py`, `main.py`, `analysis.py`, `analysis_runs` ni `/api/analyses`.
- La PR I1.4 es el punto de integración coordinado con el otro desarrollador. El worker de noticias no se convierte en worker de precios por accidente; se evaluará servicio/trabajo específico si la latencia lo requiere.
- Toda PR incluye pruebas offline, documentación y explicación de fallos parciales. Sin secretos ni payloads reales licenciados en Git.
- Leer `AGENTS.md` antes de cada tarea y añadir enlace a este plan al índice del `README.md`.

## 7. Pruebas de aceptación globales de I1

1. El sistema admite tres **fondos tradicionales indexados** reales en el catálogo sin tratarlos como ETF ni depender de bróker.
2. La batería de cobertura documenta resultados reales por ISIN y proveedor (incluidos los fallos): **no confundir capacidad anunciada con una prueba live**.
3. Diferencia claramente `NAV`, `EOD_CLOSE`, `LAST` e `INDICATIVE`, con fecha y fuente; NAV sin hora inventada.
4. Distingue `Instrument`, `Listing`, `ProviderSymbol`, `Position` y `MarketObservation`; no confunde ISIN con ticker.
5. Valora con `Decimal` y FX correctamente; no suma USD con EUR sin tasa fechada y documentada.
6. Si falta un dato, la cartera muestra `PARTIAL`/`MISSING`, nunca un total inventado ni «real time» por defecto.
7. Refrescar cotizaciones no modifica las cantidades ni reescribe informes anteriores; snapshots reproducibles.
8. La demo funciona íntegramente sin APIs privadas, credenciales, Docker obligatorio ni LLM; tests live únicamente opt-in.
9. Adaptadores no cambian el contrato de IA; cambios de contratos compartidos se aprueban mediante PR separada.
10. Se documenta la licencia y cobertura comprobadas del proveedor seleccionado; si no se puede justificar para fondos europeos, se declara **bloqueo** y se decide alternativa expresamente.

## 8. Riesgos y medidas

| Riesgo | Medida |
|---|---|
| Ningún plan asequible devuelve NAV de F01–F03 | No seleccionar proveedor; solicitar cobertura/demo; NAV manual auditado solo como modo explícito |
| Una API retorna otra clase de fondo o otra bolsa | Resolución por ISIN/share class + MIC/listing, validación de moneda, nunca matching por nombre |
| Datos EOD desfasados o fondo publica T+1/T+2 | Mostrar NAV date y retrieved_at, umbral por clase, no simular cotización intradía |
| ETC/bono representado como acción | Semántica de producto y valoración propia; estado no soportado si faltan datos |
| Licencias impiden compartir datos con equipo | Confirmación comercial y pruebas individuales; no repositorio de payloads |
| Modificar `Position`/`models.py` rompe análisis previo | Nuevo módulo + adaptador; migraciones/versiones y PR de contratos coordinada |
| Cobertura inicial baja por clases | Mostrar cobertura real; ampliar proveedores por categoría sin cambiar modelo interno |

## 9. Puntos de aprobación pendientes

- Confirmar si se autoriza **un gasto recurrente** para validar NAV europeos o si debe hacerse el primer spike solo con planes gratuitos/sandbox.
- Confirmar por escrito derechos de licencia de las APIs en entorno colaborativo de dos desarrolladores.
- Acordar `PortfolioAnalysisView v1` antes de la integración con el módulo de inteligencia.
- Ratificar que cotizaciones y posiciones se refrescarán por acciones diferentes; I1 solo incluye cotizaciones.

**Salida de I1.0:** una decisión informada de proveedor y una matriz de cobertura verificable. **Salida del I1 completo:** una cartera ficticia multiactivo que se valora (completa o parcialmente) con datos tipados, reproducibles y trazables, con fondos indexados obligatoriamente contemplados y cobertura real medida.
