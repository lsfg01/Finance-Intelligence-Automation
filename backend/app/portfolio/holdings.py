import csv
import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal, localcontext
from io import StringIO
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, StringConstraints

from .fixtures import DEMO_INSTRUMENTS, DEMO_LISTINGS
from .models import Account, CalendarDate, Currency, DomainModel, ExactDecimal, Instrument, Listing, PortfolioSnapshot, Position


class HoldingsSource(DomainModel):
    provider: Literal["investing.com", "alpaca-paper"]
    reference_date: CalendarDate | None = None
    loaded_at: AwareDatetime
    reference_origin: Literal["csv", "filename"] | None = None


class ImportFile(DomainModel):
    account: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    csv: str = Field(min_length=1, max_length=1_000_000, repr=False)
    filename: str | None = Field(default=None, max_length=255)


class ConfirmImport(ImportFile):
    preview_token: str = Field(pattern=r"^[0-9]{1,12}:[0-9a-f]{64}$")


class Money(DomainModel):
    amount: ExactDecimal
    currency: Currency


class ProfitLoss(DomainModel):
    money: Money | None = None
    percentage: ExactDecimal | None = None


class InvestingTotals(DomainModel):
    market_value: Money | None = None
    open_pnl: ProfitLoss | None = None
    daily_pnl: ProfitLoss | None = None
    total_pnl: ProfitLoss | None = None


class HoldingEconomics(DomainModel):
    average_price: Money | None = None
    current_price: Money | None = None
    market_value: Money | None = None
    commission: Money | None = None
    weight_pct: ExactDecimal | None = None
    daily_pnl: ProfitLoss | None = None
    net_pnl: ProfitLoss | None = None
    quote_time: time | None = None


class HoldingLot(DomainModel):
    quantity: ExactDecimal
    opened_on: CalendarDate | None = None
    entry_price: Money | None = None


class HoldingRow(DomainModel):
    line: int
    label: str
    exchange: str
    quantity: ExactDecimal | None
    instrument_id: str | None = None
    listing_id: str | None = None
    reference_date: CalendarDate | None = None
    issue: str | None = None
    name: str = ""
    side: Literal["long"] | None = None
    economics: HoldingEconomics | None = None
    lots: tuple[HoldingLot, ...] | None = None
    warnings: tuple[str, ...] = ()


class InvestingExport(DomainModel):
    rows: tuple[HoldingRow, ...]
    totals: InvestingTotals = InvestingTotals()
    reference_date: CalendarDate | None = None
    reference_origin: Literal["csv", "filename"] | None = None


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


HEADERS = {
    "symbol": {"symbol", "ticker", "ticker symbol", "simbolo"},
    "name": {"name", "instrument", "instrument name", "nombre", "instrumento"},
    "isin": {"isin"},
    "exchange": {"exchange", "stock exchange", "market", "bolsa", "mercado"},
    "currency": {"currency", "moneda", "divisa"},
    "quantity": {"quantity", "qty", "amount", "shares", "units", "cantidad", "acciones", "unidades"},
    "reference": {"as of", "as of date", "reference date", "fecha de referencia"},
    "side": {"side", "position", "type", "transaction type", "tipo", "tipo de transaccion", "direccion"},
}

NAME_ALIASES = {"microsoft corp": "microsoft", "microsoft corporation": "microsoft"}
INVESTING_SYMBOLS = {"MSFT.O": "MSFT", "NVDA.O": "NVDA"}
INVESTING_EXCHANGES = {("SPY", "nyse"): "NYSE Arca"}
POSITION_SECTIONS = {"resumen de posiciones", "positions summary", "position summary",
                     "posiciones abiertas", "open positions"}
POSITION_TOTALS = {"val. mercado", "valor de mercado", "market value", "b/p posic. abiertas",
                   "b/p diario", "b/p total", "open positions p/l", "daily p/l", "total p/l"}

TOTAL_KEYS = dict.fromkeys(("val. mercado", "valor de mercado", "market value"), "market_value")
TOTAL_KEYS.update(dict.fromkeys(("b/p posic. abiertas", "open positions p/l"), "open_pnl"))
TOTAL_KEYS.update(dict.fromkeys(("b/p diario", "daily p/l"), "daily_pnl"))
TOTAL_KEYS.update(dict.fromkeys(("b/p total", "total p/l"), "total_pnl"))
LOT_SECTIONS = {"posiciones abiertas", "open positions"}
OTHER_SECTIONS = {"posiciones cerradas", "closed positions", "transacciones", "transactions"}
ECONOMIC_HEADERS = {
    "average_price": {"precio medio", "average price", "avg. price"},
    "current_price": {"precio actual", "current price"},
    "market_value": {"val. mercado", "valor de mercado", "market value"},
    "commission": {"comision", "commission"},
    "weight": {"peso relativo", "weight", "weight %"},
    "daily_pnl": {"b/p diario", "daily p/l"},
    "daily_pct": {"% b/p diario", "daily p/l %"},
    "net_pnl": {"b/p neto", "net p/l"},
    "net_pct": {"% b/p neto", "net p/l %"},
    "quote_time": {"fecha/hora", "date/time"},
    "opened_on": {"fecha apertura", "open date", "opening date"},
    "entry_price": {"precio entrada", "entry price"},
}

EXCHANGES = {
    "nasdaq": "XNAS", "nasdaqgs": "XNAS", "nasdaq global select": "XNAS",
    "nasdaq global select market": "XNAS", "xnas": "XNAS",
    "xetra": "XETR", "xetr": "XETR",
    "london": "XLON", "lse": "XLON", "londres": "XLON", "xlon": "XLON",
    "madrid": "XMAD", "bolsa de madrid": "XMAD", "xmad": "XMAD",
    "nyse arca": "ARCX", "nysearca": "ARCX", "arca": "ARCX", "arcx": "ARCX",
}


def resolve_holding(
    *, symbol: str, exchange: str, currency: str = "", isin: str = "", name: str = ""
) -> tuple[Instrument | None, Listing | None, str | None]:
    tickers = tuple(listing for listing in DEMO_LISTINGS if listing.ticker == symbol.upper())
    ticker_ids = {listing.instrument_id for listing in tickers}
    name = normalize(name).rstrip(".")
    name = NAME_ALIASES.get(name, name)
    named_ids = {item.instrument_id for item in DEMO_INSTRUMENTS if name == normalize(item.name)}
    candidates = [
        instrument for instrument in DEMO_INSTRUMENTS
        if (not isin or instrument.isin == isin.upper())
        and (not named_ids or instrument.instrument_id in named_ids)
        and (isin or named_ids or ticker_ids)
        and (not symbol or instrument.instrument_id in ticker_ids)
    ]
    mic = EXCHANGES.get(normalize(exchange))
    if mic:
        ids = {listing.instrument_id for listing in DEMO_LISTINGS if listing.mic == mic}
        candidates = [item for item in candidates if item.instrument_id in ids] or candidates
    if len(candidates) != 1:
        return None, None, "Instrumento desconocido o ambiguo en el catálogo I1"
    instrument = candidates[0]
    listings = [
        listing for listing in DEMO_LISTINGS if listing.instrument_id == instrument.instrument_id
    ]
    if not listings:
        if exchange or (currency and instrument.share_class_currency != currency.upper()):
            return instrument, None, "Plaza o moneda incompatible con el instrumento"
        return instrument, None, None
    matching = [
        listing for listing in listings
        if listing.mic == mic and (not symbol or listing.ticker == symbol.upper())
        and (not currency or listing.currency == currency.upper())
    ]
    if len(matching) != 1:
        return instrument, None, "Plaza ambigua o incompatible. Indica la bolsa del instrumento"
    return instrument, matching[0], None


def _number(value: str, *, quantity: bool = False) -> Decimal:
    value = value.replace("−", "-").strip()
    if not quantity and re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?", value):
        value = value.replace(".", "")
    if len(value) > 30 or not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", value):
        raise ValueError("formato numérico inválido")
    return Decimal(value.replace(",", "."))


_CURRENCIES = {"€": "EUR", "£": "GBP", "US$": "USD", "C$": "CAD", "A$": "AUD"}


def _money(value: str, fallback: str | None = None) -> Money:
    match = re.fullmatch(r"(?:(US\$|C\$|A\$|[$€£]|[A-Z]{3})\s*)?([+−\-\d.,]+)\s*"
                         r"(US\$|C\$|A\$|[$€£]|[A-Z]{3})?", value)
    if not match:
        raise ValueError("importe inválido")
    prefix, amount, suffix = match.groups()
    marker = prefix or suffix
    if marker == "$":
        currency = fallback if fallback in {"USD", "CAD", "AUD", "NZD", "HKD", "SGD", "MXN"} else None
    else:
        currency = _CURRENCIES.get(marker, marker) if marker else fallback
    if not currency or (prefix and suffix and prefix != suffix):
        raise ValueError("divisa no identificada")
    return Money(amount=_number(amount), currency=currency)


def _pct(value: str) -> Decimal:
    return _number(value.removesuffix("%").strip(), quantity=True)


def _total_pnl(value: str) -> ProfitLoss:
    parts = re.fullmatch(r"(.+?)\s*/\s*([+−\-\d.,]+\s*%)\s*(.*)", value)
    if not parts:
        return ProfitLoss(money=_money(value))
    amount, percentage, currency = parts.groups()
    return ProfitLoss(money=_money(f"{amount} {currency}".strip()), percentage=_pct(percentage))


def _values(fields: dict[str, str], key: str, read, warnings: list[str]):
    value = fields.get(key, "")
    if value in {"", "--", "-", "—"}:
        return None
    try:
        return read(value)
    except ValueError:
        warnings.append(f"Dato opcional inválido: {key}")
        return None


def _open_date(value: str) -> date:
    if "/" in value:
        return datetime.strptime(value, "%d/%m/%Y").date()
    return date.fromisoformat(value)


def _read_row(line: int, fields: dict[str, str], *, lot: bool) -> tuple[HoldingRow, HoldingLot | None]:
    try:
        quantity = _number(fields["quantity"], quantity=True)
    except ValueError:
        quantity = None
    exchange, symbol, name = (fields.get(key, "") for key in ("exchange", "symbol", "name"))
    ticker = INVESTING_SYMBOLS.get(symbol.upper(), symbol)
    instrument, listing, resolution_issue = resolve_holding(
        symbol=ticker, exchange=INVESTING_EXCHANGES.get((ticker.upper(), normalize(exchange)), exchange),
        currency=fields.get("currency", ""), isin=fields.get("isin", ""), name=name,
    )
    currency = listing.currency if listing else instrument.share_class_currency if instrument else None
    side = normalize(fields.get("side", ""))
    is_long = side in {"long", "buy", "compra", "largo"} or "side" not in fields
    warnings: list[str] = []
    reference = _values(fields, "reference", date.fromisoformat, warnings)
    issues = [
        "Cantidad inválida" if quantity is None or quantity <= 0 else None,
        "Tipo de posición incompatible con tenencias largas" if not is_long else None,
        "Fecha de referencia inválida" if warnings else None,
        resolution_issue,
    ]
    def money(key: str, fallback: str | None = None) -> Money | None:
        return _values(fields, key, lambda value: _money(value, fallback), warnings)

    def pnl(key: str) -> ProfitLoss | None:
        amount = money(f"{key}_pnl")
        percentage = _values(fields, f"{key}_pct", _pct, warnings)
        return ProfitLoss(money=amount, percentage=percentage) if amount is not None or percentage is not None else None

    economics = None
    detail = None
    if lot and quantity is not None:
        detail = HoldingLot(quantity=quantity, opened_on=_values(fields, "opened_on", _open_date, warnings),
                            entry_price=money("entry_price", currency))
    if not lot:
        economics = HoldingEconomics(
            average_price=money("average_price", currency), current_price=money("current_price", currency),
            market_value=money("market_value", currency), commission=money("commission", currency),
            weight_pct=_values(fields, "weight", _pct, warnings), daily_pnl=pnl("daily"), net_pnl=pnl("net"),
            quote_time=_values(fields, "quote_time", time.fromisoformat, warnings),
        )
        price, value = economics.current_price, economics.market_value
        if quantity is not None and price and value and price.currency == value.currency:
            with localcontext() as context:
                context.prec = 38
                if abs(quantity * price.amount - value.amount) > Decimal("0.01"):
                    warnings.append("El valor declarado difiere de cantidad por precio actual")
    return HoldingRow(
        line=line, label=symbol or name or fields.get("isin", ""), name=name, exchange=exchange,
        quantity=quantity, reference_date=reference,
        instrument_id=instrument.instrument_id if instrument else None,
        listing_id=listing.listing_id if listing else None, side="long" if is_long else None,
        issue=" · ".join(issue for issue in issues if issue) or None, economics=economics,
        warnings=tuple(warnings),
    ), detail


def _columns(header: list[str]) -> dict[str, int]:
    values = [normalize(value) for value in header]
    indexes = {}
    for key, aliases in (HEADERS | ECONOMIC_HEADERS).items():
        matches = [index for index, value in enumerate(values) if value in aliases]
        if len(matches) > 1:
            raise ValueError(f"El CSV contiene columnas duplicadas para {key}")
        if matches:
            indexes[key] = matches[0]
    return indexes


def _has_holdings_columns(columns: dict[str, int]) -> bool:
    return "quantity" in columns and bool(columns.keys() & {"symbol", "isin", "name"})


def _reference_from_filename(filename: str) -> date | None:
    match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2}|\d{8})(?=\.csv$)", filename, re.I)
    if match:
        try:
            return date.fromisoformat(match[1]) if "-" in match[1] else datetime.strptime(match[1], "%d%m%Y").date()
        except ValueError:
            pass
    return None


def read_investing(text: str, filename: str = "") -> InvestingExport:
    text = text.removeprefix("\ufeff")
    for delimiter in (",", ";", "\t"):
        reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True)
        try:
            header = next((row for row in reader if any(cell.strip() for cell in row)), [])
            if len(header) == 1 and normalize(header[0]) in POSITION_SECTIONS:
                header = next((row for row in reader if any(cell.strip() for cell in row)), [])
        except csv.Error:
            continue
        if _has_holdings_columns(_columns(header)):
            break
    else:
        raise ValueError("El CSV Holdings necesita una columna de cantidad y otra de símbolo, nombre o ISIN")

    summary: list[HoldingRow] = []
    details: list[tuple[HoldingRow, HoldingLot | None]] = []
    totals = {}
    section = "summary"
    section_label = "Resumen de posiciones"
    expect_header = True
    saw_lots = False
    width = 0
    indexes = {}
    reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True)
    for cells in reader:
        if not any(value.strip() for value in cells):
            continue
        label = normalize(cells[0])
        if len(cells) == 1 and label in POSITION_SECTIONS | OTHER_SECTIONS:
            section_label = cells[0]
            section = "lots" if label in LOT_SECTIONS else "summary" if label in POSITION_SECTIONS else "other"
            saw_lots |= section == "lots"
            expect_header = True
            continue
        if section == "other":
            continue
        if len(cells) == 2 and label in POSITION_TOTALS:
            if section == "summary" and cells[1].strip() not in {"", "--", "-", "—"}:
                key = TOTAL_KEYS[label]
                try:
                    totals[key] = _money(cells[1].strip()) if key == "market_value" else _total_pnl(cells[1].strip())
                except ValueError:
                    raise ValueError(f"{section_label}, fila {reader.line_num}: total {cells[0]} inválido") from None
            continue
        if expect_header or any(normalize(cell) in HEADERS["quantity"] for cell in cells):
            candidate = _columns(cells)
            if expect_header and not _has_holdings_columns(candidate):
                raise ValueError(f"{section_label}, fila {reader.line_num}: cabecera sin cantidades o instrumentos")
            if _has_holdings_columns(candidate):
                width, indexes, expect_header = len(cells), candidate, False
                continue
        if len(cells) != width:
            raise ValueError(f"{section_label}, fila {reader.line_num}: número de columnas inesperado")
        fields = {key: cells[index].strip() for key, index in indexes.items()}
        row, lot = _read_row(reader.line_num, fields, lot=section == "lots")
        if section == "lots":
            details.append((row, lot))
        else:
            summary.append(row)
    if not summary:
        raise ValueError("Resumen de posiciones: el archivo no contiene posiciones con cantidades")

    def identity(row: HoldingRow) -> tuple[str | None, str | None]:
        return row.instrument_id, row.listing_id

    keys = {identity(row) for row in summary if row.instrument_id is not None}
    lots_by_key: dict[tuple, list[HoldingLot]] = {}
    for row, lot in details:
        if row.issue or lot is None or identity(row) not in keys:
            issue = row.issue or "Lote sin posición correspondiente en el resumen"
            raise ValueError(f"Posiciones abiertas, fila {row.line}: {issue}")
        lots_by_key.setdefault(identity(row), []).append(lot)
    seen: set[tuple] = set()
    rows = []
    with localcontext() as context:
        context.prec = 38
        for row in summary:
            key = identity(row)
            lots = tuple(lots_by_key.get(key, ())) if saw_lots else None
            issue = row.issue
            if not issue and key in seen:
                issue = "Posición duplicada en el resumen"
            if not issue and lots is not None and sum(lot.quantity for lot in lots) != row.quantity:
                issue = "Las cantidades de los lotes no coinciden con la posición"
            rows.append(row.model_copy(update={"lots": lots, "issue": issue}))
            seen.add(key)
    references = {row.reference_date for row in rows if row.reference_date is not None}
    if len(references) > 1:
        raise ValueError("Resumen de posiciones: las fechas de referencia deben coincidir")
    reference = next(iter(references), None)
    origin = "csv" if reference else None
    if not reference and (reference := _reference_from_filename(filename)) is not None:
        origin = "filename"
    if reference:
        rows = [row.model_copy(update={"reference_date": reference}) for row in rows]
    return InvestingExport(rows=tuple(rows), totals=InvestingTotals(**totals),
                           reference_date=reference, reference_origin=origin)


def build_holdings(
    account: Account, rows: tuple[HoldingRow, ...], provider: Literal["investing.com", "alpaca-paper"],
    loaded_at: datetime, *, base_currency: str = "EUR",
) -> tuple[PortfolioSnapshot, HoldingsSource]:
    quantities: dict[tuple[str, str | None, date], Decimal] = {}
    references = [row.reference_date for row in rows if row.reference_date is not None]
    if any(reference > loaded_at.date() for reference in references):
        raise ValueError("La fecha de referencia es posterior a la carga")
    reference = max(references) if rows and len(references) == len(rows) else None
    as_of = reference or loaded_at.date()
    with localcontext() as context:
        context.prec = 38
        for row in rows:
            if row.issue or row.instrument_id is None or row.quantity is None:
                raise ValueError("La carga contiene posiciones sin resolver")
            key = (row.instrument_id, row.listing_id, row.reference_date or as_of)
            quantities[key] = quantities.get(key, Decimal(0)) + row.quantity
    return PortfolioSnapshot(
        snapshot_id=str(uuid4()), portfolio_id=account.account_id, version=1,
        base_currency=base_currency, accounts=(account,), as_of=as_of, is_simulated=True,
        positions=tuple(
            Position(position_id=f"{account.account_id}:{listing or instrument}:{day}", account_id=account.account_id,
                     instrument_id=instrument, listing_id=listing, quantity=quantity, as_of=day)
            for (instrument, listing, day), quantity in quantities.items()
        ),
    ), HoldingsSource(provider=provider, reference_date=reference, loaded_at=loaded_at)
