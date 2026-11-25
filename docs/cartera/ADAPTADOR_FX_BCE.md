# I1.2 · Tipo de cambio de referencia del BCE

`ECBFXProvider().get_rate("EUR", "USD", fecha)` consulta la serie diaria `EXR.D.USD.EUR.SP00.A` y devuelve una `FXObservation`. La tasa es un `Decimal` en **USD por 1 EUR**. `as_of` conserva la fecha efectiva de la observación y `retrieved_at` registra la recuperación en UTC. La observación incluye la URL de la serie y las condiciones de uso. [Documentación del BCE](https://data.ecb.europa.eu/help/api/data).

Una consulta en domingo puede devolver la referencia del viernes con fecha efectiva del viernes. Si faltan observaciones válidas hasta la fecha solicitada, el resultado es `None`. Este adaptador expone el único par EUR/USD. La conversión y la vigencia de la tasa para cada precio corresponden al motor de valoración.

El BCE devuelve HTTP 404 cuando la consulta carece de resultados. Otros errores HTTP y los fallos de transporte se propagan al llamador. [Códigos de estado del BCE](https://data.ecb.europa.eu/help/api/status-codes).

Las pruebas usan respuestas HTTP simuladas y se ejecutan offline.

```bash
python -m pytest -q tests/test_market_data_ecb.py
```
