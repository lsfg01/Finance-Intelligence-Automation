import json
import re
from decimal import Decimal
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from .holdings import HoldingRow, resolve_holding
from .models import Account


PAPER_API = "https://paper-api.alpaca.markets"
AUTHORIZE_URL = "https://app.alpaca.markets/oauth/authorize"
TOKEN_URL = "https://api.alpaca.markets/oauth/token"


class AlpacaError(Exception):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(request: Request) -> object:
    try:
        with build_opener(NoRedirects()).open(request, timeout=10) as response:
            if response.status != 200:
                raise AlpacaError("Respuesta incompleta de Alpaca")
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise AlpacaError("Respuesta de Alpaca demasiado grande")
            return json.loads(body)
    except HTTPError as error:
        error.close()
        if error.code in (401, 403):
            raise AlpacaError("Alpaca rechazó la autorización. Conecta de nuevo la cuenta Paper") from None
        raise AlpacaError("No se pudo completar la consulta a Alpaca") from None
    except (OSError, HTTPException, ValueError):
        raise AlpacaError("No se pudo leer la respuesta de Alpaca") from None


def exchange_code(code: str, client_id: str, secret: str, redirect_uri: str) -> str:
    result = request_json(Request(TOKEN_URL, data=urlencode({
        "grant_type": "authorization_code", "code": code, "client_id": client_id,
        "client_secret": secret, "redirect_uri": redirect_uri,
    }).encode("ascii"), headers={"Content-Type": "application/x-www-form-urlencoded"}))
    if not isinstance(result, dict) or result.get("scope", "") != "":
        raise AlpacaError("La autorización de Alpaca debe limitarse a lectura")
    token = result.get("access_token")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
        raise AlpacaError("Alpaca no devolvió una autorización válida")
    return token


def read_account(token: str) -> tuple[Account, str]:
    data = request_json(Request(f"{PAPER_API}/v2/account", headers={"Authorization": f"Bearer {token}"}))
    try:
        account_id = UUID(data["id"])
        currency = data["currency"]
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AlpacaError("Alpaca no devolvió una cuenta Paper válida") from None
    return Account(account_id=f"alpaca-paper:{account_id}", name=f"Alpaca Paper · {account_id.hex[:8]}"), currency


def read_positions(token: str) -> tuple[HoldingRow, ...]:
    data = request_json(Request(f"{PAPER_API}/v2/positions", headers={"Authorization": f"Bearer {token}"}))
    if not isinstance(data, list):
        raise AlpacaError("Alpaca no devolvió una lista completa de posiciones")
    rows = []
    seen = set()
    for index, item in enumerate(data, 1):
        try:
            asset_id = UUID(item["asset_id"])
            symbol, exchange, qty = item["symbol"], item["exchange"], item["qty"]
            asset_class = item["asset_class"]
            if (not re.fullmatch(r"[A-Z0-9./_-]{1,32}", symbol)
                    or (exchange is not None and not isinstance(exchange, str))
                    or not isinstance(asset_class, str) or not asset_class
                    or len(qty) > 30 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", qty)
                    or item["side"] != "long" or asset_id in seen):
                raise ValueError
            quantity = Decimal(qty)
            if quantity <= 0:
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            raise AlpacaError(f"Posición {index} incompleta, duplicada o incompatible con tenencias largas") from None
        seen.add(asset_id)
        instrument, listing, issue = resolve_holding(
            symbol=symbol if asset_class == "us_equity" else "", exchange=exchange or "",
        )
        rows.append(HoldingRow(
            line=index, label=symbol, exchange=exchange or "", quantity=quantity,
            instrument_id=instrument.instrument_id if instrument and not issue else f"alpaca:{asset_id}:{symbol}",
            listing_id=listing.listing_id if listing else None,
        ))
    return tuple(rows)
