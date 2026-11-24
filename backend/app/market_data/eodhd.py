import json
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.portfolio.models import MarketObservation, PriceType


EOD_URL = "https://eodhd.com/api/eod"
LICENSE_URL = "https://eodhd.com/help/commercial"


class EODHDPriceProvider:
    """Lee observaciones diarias de símbolos cuya identidad ya se ha verificado."""

    def __init__(self, token: str, timeout: float = 5.0):
        self.token = token
        self.timeout = timeout

    def get_latest(
        self,
        *,
        symbol: str,
        instrument_id: str,
        listing_id: str | None,
        currency: str,
        price_type: PriceType,
        start: date,
        end: date,
    ) -> MarketObservation | None:
        source = f"{EOD_URL}/{symbol}"
        query = urlencode({
            "api_token": self.token, "fmt": "json", "period": "d",
            "from": start.isoformat(), "to": end.isoformat(),
        })
        request = Request(f"{source}?{query}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response, parse_float=Decimal)
            retrieved_at = datetime.now(timezone.utc)

        if not isinstance(payload, list):
            raise ValueError("Respuesta diaria de EODHD inválida")
        closes: dict[date, Decimal | int] = {}
        for row in payload:
            if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                raise ValueError("Fecha diaria de EODHD ausente")
            effective_date = date.fromisoformat(row["date"])
            if effective_date.isoformat() != row["date"]:
                raise ValueError("Fecha diaria de EODHD inválida")
            if not start <= effective_date <= end:
                continue
            close = row.get("close")
            if type(close) not in (int, Decimal) or not Decimal(close).is_finite() or close <= 0:
                raise ValueError("Precio diario de EODHD inválido")
            if closes.setdefault(effective_date, close) != close:
                raise ValueError("Precios diarios contradictorios en EODHD")

        if not closes:
            return None
        effective_date = max(closes)
        return MarketObservation(
            observation_id=f"EODHD:{symbol}:{effective_date}:{uuid4()}",
            instrument_id=instrument_id,
            listing_id=listing_id,
            value=closes[effective_date],
            currency=currency,
            price_type=price_type,
            price_as_of=effective_date,
            retrieved_at=retrieved_at,
            provider="EODHD",
            source=source,
            license=LICENSE_URL,
            is_simulated=False,
        )
