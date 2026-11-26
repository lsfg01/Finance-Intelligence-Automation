# Cierre de la demo de cartera de Investing.com

La importación de Holdings y el análisis basado en la cartera importada quedaron aceptados manualmente por el usuario el 26 de noviembre de 2026. Se implementaron en `feat/cartera-importacion-paper` a partir del plan de la demo de Investing.com y del [cierre de I1](../I1/CIERRE_I1_CARTERA_Y_PRECIOS.md).

## Recorrido entregado

| Acción | Resultado |
|---|---|
| **Importar cartera** | La vista previa muestra cantidades, lotes, cotizaciones, totales declarados e incidencias. Confirmar guarda y activa las posiciones y su valoración en una transacción. La misma exportación conserva la versión y la valoración. Una exportación nueva sustituye las tenencias activas de su cuenta y conserva el histórico. |
| **Actualizar precios** | Solicita cotizaciones a EODHD y tipos de cambio al BCE cuando proceda. Un refresco correcto guarda otra valoración de la misma versión de posiciones. Los importes declarados y el B/P del CSV conservan la referencia de la exportación. El usuario puede volver a consultar la valoración importada. |
| **Analizar cartera** | La petición fija cartera, versión, valoración, perfil y documentos. El worker valida un contexto de prueba versionado con `PortfolioAnalysisView v1`, ejecuta el consumidor determinista y guarda el informe inmutable. El recorrido v1.1 y los informes históricos de I0 siguen disponibles. |

La muestra tiene **20 SPY, 5 MSFT y 10 NVDA** en tres posiciones y tres lotes. Los valores por posición suman **17.922,40 USD**. Investing declara **16.320,14 EUR** de valor y **+19,71 EUR (+0,12 %)** de B/P abierto. El total calculado en EUR queda indeterminado por falta de conversiones por posición. El informe recupera las **5 acciones de Microsoft** y su **peso directo declarado del 13,48 %**. La exposición indirecta queda desconocida por falta del desglose de SPY.

## Evidencia de aceptación

| Comprobación | Resultado |
|---|---|
| Chrome y CSV nativo | Vista previa, confirmación y recuperación tras recargar. La importación generó 0 trabajos, 0 consultas a EODHD y 0 al BCE. |
| Chrome, API y worker local | Un clic y `python -m app.worker --once` dejaron 1 trabajo y 1 informe persistido. EODHD y BCE registraron 0 consultas durante el análisis. |
| Chrome a 390 px | Diálogo operado con teclado. Escape canceló la vista previa y devolvió el foco sin cambiar la cartera. |
| Refresco controlado | El fallo conservó la valoración del CSV. El éxito guardó otra valoración. Se registraron 6 consultas simuladas a EODHD y 1 al BCE entre ambos intentos, con 0 trabajos adicionales. |
| Pruebas automatizadas | `python -m pytest -q` pasó con **113 pruebas**. Incluye precisión decimal, rechazos, doble envío, reimportación, aislamiento de snapshots y lectura de informes I0. |

| Referencia de la ejecución en Chrome | Identificador |
|---|---|
| Cartera y versión | `investing:9b10b155774563267d60422295b418a9366dee95b5dc6d53a52da72d769ab3dd`, v1 |
| Valoración importada | `870f5bed-4327-4567-a1cb-61d9c40c780c` |
| Trabajo | `3b4edaf4-dc42-4379-b595-3d1e267f0ed9` |
| Informe | `e8b7e543-a81d-419a-bc01-46b1e925c9f2` |
| Valoración del refresco controlado | `8fddc1b4-b3c4-48cf-b512-4e345f8974d6` |

El [CSV de regresión](../../../tests/fixtures/investing_holdings_demo_25112026.csv), las [pruebas de aceptación](../../../tests/test_investing_acceptance.py) y el [ejemplo tipado de entrada y salida](../../ejemplos/analisis_cartera_importada_demo.json) permiten reproducir el comportamiento offline. El [README](../../../README.md#cargar-carteras-ficticias-desde-el-dashboard) explica el uso de la demo.

## Continuidad

El siguiente incremento es el módulo de fuentes. El backend dispone de un documento ficticio inicial y fija los documentos disponibles al encolar. La selección de fuentes, sus derechos de uso y la integración del consumidor definitivo quedan para decisiones posteriores. La conexión con Alpaca Paper aparece deshabilitada en el diálogo. El caso de 2,5 MSFT por cuenta está cubierto con datos simulados y queda pendiente repetirlo con una cuenta Paper autenticada. [Punto de entrada para la siguiente sesión](../../../AGENTS.md#siguiente-incremento-módulo-de-fuentes) · [Decisiones pendientes](../../arquitectura/DECISIONES_PENDIENTES.md).
