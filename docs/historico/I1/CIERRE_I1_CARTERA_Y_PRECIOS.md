# I1 · Cierre de cartera y datos de mercado

**Cerrado funcionalmente el 23 de noviembre de 2026** en el entorno local de la rama `feat/cartera-dominio`. Integrado en `main` el 24 de noviembre de 2026 mediante la [PR 3](https://github.com/lsfg01/Finance-Intelligence-Automation/pull/3).

La demo muestra 11 posiciones con cantidades ficticias y permite valorarlas con precios de mercado. Al abrir la cartera, el dashboard recupera de SQLite las posiciones y la última valoración de esa versión. Al pulsar **Actualizar precios**, el backend consulta los proveedores, calcula los importes en euros y guarda una nueva valoración. El refresco conserva las cantidades y los informes históricos.

## Qué se entregó

| Entrega | Resultado | Trazabilidad |
|---|---|---|
| I1.0 · Proveedores | EODHD para precios y valores liquidativos (NAV). BCE para el cambio de referencia. EODHD resolvió los diez ISIN de la muestra. Vanguard corroboró F01 y F03 en las cinco fechas probadas. Para F02, los 13,4877 EUR del 20/11 redondearon a los 13,49 EUR publicados por Fidelity. | ADR 0001 y matriz del estudio |
| I1.1 · Dominio | Instrumentos, plazas de cotización, posiciones y observaciones diferenciados. La cartera admite varias plazas para un ISIN y dispone de datos simulados para pruebas offline. | `e7131ea` |
| I1.2 · Tipo de cambio | Observación del BCE en USD por 1 EUR con fecha efectiva e instante de recuperación en UTC. El motor divide el importe en USD por la tasa para obtener EUR. | `32cc47c` |
| I1.3 · Motor de valoración | Cálculo con `Decimal` y snapshots inmutables en SQLite. Cada valoración identifica la versión de cartera y las observaciones de precio y cambio utilizadas. | `641d804` |
| I1.4 · API y dashboard | Refresco manual, presentación del valor conocido y la cobertura, y recuperación de la valoración guardada. | `e111783` |
| I1.5 · Contrato para análisis | `PortfolioAnalysisView v1` reúne cartera, valoración, referencias de precios y cambio, y composición disponible. El ejemplo JSON se puede leer sin arrancar la API ni abrir SQLite. | `43642d9` |
| Integración del flujo | La pantalla inicial y el refresco usan la misma cartera de SQLite. El adaptador consulta la clase de fondo o la plaza correspondiente. | `0f21957` y `60d0889` |
| Bitcoin (K01) | Se incorporó la cotización directa en EUR de `BTC-EUR.CC` de EODHD. El dashboard muestra la fecha, el tipo de precio y el estado de la posición. | Fila de mercado comprobada al cierre |

El refresco toma la fecha UTC de ejecución. Para los fondos y valores cotizados, busca el último NAV o cierre disponible en la ventana de siete días que termina en esa fecha. La pantalla distingue precios simulados y de mercado y conserva la fecha efectiva de la observación. Para una posición en USD se usa el cambio del BCE disponible en la fecha del precio. Si falta una observación necesaria, la cartera presenta el importe conocido y mantiene el total indeterminado (`total_value=None`).

## Evidencia de aceptación

| Comprobación | Resultado observado |
|---|---|
| Cálculo y cobertura parcial | 2 unidades × 110 USD ÷ 1,10 = **200 EUR**. Al añadir una posición sin precio, el resultado fue **1 de 2** posiciones valoradas, estado `PARTIAL`, 200 EUR conocidos y total indeterminado. |
| Inmutabilidad y plaza | Tras guardar dos valoraciones y reabrir SQLite, la primera conservó los 200 EUR, la versión 1 de cartera y sus referencias originales. Una posición con varias plazas y sin plaza elegida conservó el estado `AMBIGUOUS_LISTING` aunque solo hubiera precio en una de ellas. |
| Modo simulado | **10 de 11** posiciones y **4.427,05 EUR conocidos**. El fixture dejó sin precio MyInvestor Cartera Permanente (F04). |
| Primer refresco de mercado del 23/11, verificado en Chrome | **10 de 11** posiciones y **6.085,03 EUR conocidos**, con total indeterminado. Fidelity (F02) y MyInvestor (F04) utilizaron NAV del viernes 20/11. Microsoft utilizó el cierre en USD de ese viernes y cambio del BCE. Bitcoin aún estaba pendiente de asociar a un símbolo del proveedor. |
| Refresco completo del 23/11 tras integrar Bitcoin | **11 de 11** posiciones valoradas, estado `COMPLETE` y total calculado. Los **0,0125 BTC** a **54.790,3671875 EUR/BTC** dieron **684,88 EUR** tras el redondeo. EODHD, **precio indicativo** del **22/11/2026**. |

La valoración completa se recuperó de SQLite por API con el identificador `f9929da7-bff2-4bcb-9688-229f6548c8f2`.

La versión de cierre superó **53 pruebas automatizadas en Docker**, con respuestas simuladas de EODHD y del BCE. El recorrido real se comprobó desde el navegador. También se verificó el arranque con un volumen de I0 y la recuperación de la valoración y el informe histórico tras reiniciar.

## Operación y trabajo posterior

La activación de mercado se describe en el README. La credencial se configura en el entorno local del backend, fuera del control de versiones.

- **Posiciones del usuario.** El siguiente trabajo propuesto es importar posiciones desde CSV y valorarlas con el mismo flujo.
- **Análisis de inteligencia.** El botón **Analizar cartera** sigue usando I0. Está pendiente conectar el pipeline a `PortfolioAnalysisView v1`.
- **Uso compartido.** Queda pendiente confirmar con EODHD las condiciones de uso de datos por el equipo. El cierre documentado corresponde al entorno local.

## Referencias

- [Activación y uso del dashboard](../../../README.md)
- [Decisión de proveedor](../../adr/0001-market-data-provider.md)
- [Adaptador de tipos de cambio del BCE](../../cartera/ADAPTADOR_FX_BCE.md)
- [Contrato de cartera para análisis y ejemplo JSON](../../cartera/CONTRATO_CARTERA_ANALISIS_V1.md)
- [Plan original de I1](PLAN_I1_DATOS_MERCADO_Y_CARTERA.md)
- [Matriz del estudio y contrastes con las gestoras](RESULTADOS_SPIKE_I1.md)
