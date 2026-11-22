from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.portfolio.models import FXObservation


SERIES_ID = "EXR.D.USD.EUR.SP00.A"
SERIES_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
LICENSE_URL = "https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html"


class ECBFXProvider:
    """Obtiene la referencia diaria del BCE en USD por 1 EUR."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def get_rate(self, base: str, quote: str, as_of: date) -> FXObservation | None:
        """Devuelve la última observación hasta as_of, con su fecha efectiva."""
        if (base, quote) != ("EUR", "USD"):
            return None

        query = urlencode({
            "endPeriod": as_of.isoformat(),
            "lastNObservations": 1,
            "format": "csvdata",
        })
        request = Request(f"{SERIES_URL}?{query}", headers={"Accept": "text/csv"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                retrieved_at = datetime.now(timezone.utc)
        except HTTPError as error:
            if error.code != 404:
                raise
            error.close()
            return None

        selected = _latest_rate(payload.decode("utf-8-sig"), as_of)
        if selected is None:
            return None

        effective_date, rate = selected
        return FXObservation(
            observation_id=f"ECB:{SERIES_ID}:{effective_date}:{retrieved_at.isoformat()}",
            provider="ECB",
            source=SERIES_URL,
            license=LICENSE_URL,
            retrieved_at=retrieved_at,
            is_simulated=False,
            base_currency=base,
            quote_currency=quote,
            rate=rate,
            as_of=effective_date,
        )


def _latest_rate(payload: str, as_of: date) -> tuple[date, Decimal] | None:
    if not payload.strip():
        return None

    rows = csv.DictReader(StringIO(payload), strict=True)
    if not {"KEY", "TIME_PERIOD", "OBS_VALUE"}.issubset(rows.fieldnames or ()):
        raise ValueError("El CSV del BCE carece de las columnas requeridas")

    rates: dict[date, Decimal] = {}
    for row in rows:
        if row["KEY"] != SERIES_ID:
            raise ValueError("El CSV del BCE contiene una serie inesperada")
        if row["TIME_PERIOD"] is None or row["OBS_VALUE"] is None:
            raise ValueError("El CSV del BCE contiene una fila incompleta")
        effective_date = date.fromisoformat(row["TIME_PERIOD"])
        if effective_date > as_of or not row["OBS_VALUE"].strip():
            continue

        try:
            rate = Decimal(row["OBS_VALUE"])
        except InvalidOperation as error:
            raise ValueError("El BCE devolvió una tasa inválida") from error
        if not rate.is_finite() or rate <= 0:
            raise ValueError("El BCE devolvió una tasa inválida")
        if rates.setdefault(effective_date, rate) != rate:
            raise ValueError("El BCE devolvió tasas distintas para la misma fecha")

    latest = max(rates, default=None)
    return (latest, rates[latest]) if latest is not None else None
