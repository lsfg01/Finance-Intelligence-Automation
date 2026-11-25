# I1.5 · Contrato de cartera para análisis

`PortfolioAnalysisView` es una entrada inmutable y versionada que un consumidor puede validar a partir de JSON. El orquestador prepara el objeto con los snapshots ya calculados. El contrato está disponible para revisión y consumo offline. Su adopción por el pipeline de inteligencia queda pendiente de coordinación.

| Campo | Contenido |
|---|---|
| `contract_version` | Cadena obligatoria `"1"`. |
| `portfolio` | Snapshot de cartera, versión, divisa base, cuentas, posiciones y fecha de tenencias. |
| `valuation` | Snapshot tipado con fechas de valoración y cálculo, valor conocido, total si procede, cobertura por posiciones, motivos de ausencia y observaciones de precio y FX utilizadas. |
| `instruments`, `listings` | Catálogo disponible para interpretar identificadores, plazas y monedas del snapshot. Tuplas vacías si falta el catálogo. |
| `compositions` | Composiciones disponibles hasta el corte. Cada registro conserva fuente, fecha y peso conocido. `known_weight: null` representa peso desconocido. Una lista vacía indica ausencia de observaciones. |

Los importes, cantidades, tasas y pesos fraccionarios se intercambian como cadenas decimales. Las fechas de NAV pueden conservarse sin hora. `valuation.total_value` es `null` con cobertura parcial o ausente. Un cambio incompatible en la forma o el significado del mensaje requiere una versión nueva.

El [ejemplo JSON completo](../../tests/fixtures/portfolio_analysis_v1.json) fija tres posiciones simuladas, una valoración parcial, una observación FX para la posición de Londres y composiciones de cobertura parcial y desconocida. Se puede consumir sin arrancar FastAPI, abrir SQLite ni consultar proveedores.

```python
from pathlib import Path
from app.portfolio.analysis_view import PortfolioAnalysisView

view = PortfolioAnalysisView.model_validate_json(
    Path("tests/fixtures/portfolio_analysis_v1.json").read_bytes()
)
```

El worker todavía prepara el [contexto de inteligencia](../inteligencia/CONTRATO_DATOS_UNIFICADO.md) con I0. Al conectar I1, el adaptador debe conservar el total indeterminado cuando la cobertura sea parcial y comprobar que cada referencia de precio o FX exista en las observaciones del snapshot. Hoy el lector de la vista puede aceptar una referencia ausente.
