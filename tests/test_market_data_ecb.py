from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.market_data import ecb
from app.portfolio.models import FXObservation


VIERNES = date(2024, 1, 12)
DOMINGO = date(2024, 1, 14)
LUNES = date(2024, 1, 15)
ENCABEZADO = "KEY,TIME_PERIOD,OBS_VALUE\n"


def simular_csv(monkeypatch, *filas):
    peticiones = []
    contenido = ENCABEZADO + "".join(f"{ecb.SERIES_ID},{fecha},{tasa}\n" for fecha, tasa in filas)

    def abrir(peticion, *, timeout):
        peticiones.append((peticion, timeout))
        return BytesIO(contenido.encode("utf-8"))

    monkeypatch.setattr(ecb, "urlopen", abrir)
    return peticiones


def test_domingo_conserva_la_fecha_del_viernes(monkeypatch):
    peticiones = simular_csv(
        monkeypatch, (LUNES, "1.20"), (VIERNES, "1.1000"), (date(2024, 1, 11), "1.09")
    )
    antes = datetime.now(timezone.utc)
    observacion = ecb.ECBFXProvider(timeout=2).get_rate("EUR", "USD", DOMINGO)
    despues = datetime.now(timezone.utc)

    assert isinstance(observacion, FXObservation)
    assert observacion.as_of == VIERNES
    assert observacion.rate == Decimal("1.1000")
    assert observacion.rate.as_tuple().exponent == -4
    assert (observacion.base_currency, observacion.quote_currency) == ("EUR", "USD")
    assert observacion.provider == "ECB"
    assert observacion.source == ecb.SERIES_URL
    assert observacion.license == ecb.LICENSE_URL
    assert observacion.retrieved_at.tzinfo is timezone.utc
    assert antes <= observacion.retrieved_at <= despues
    assert not observacion.is_simulated

    [(peticion, timeout)] = peticiones
    url = urlsplit(peticion.full_url)
    assert f"{url.scheme}://{url.netloc}{url.path}" == ecb.SERIES_URL
    assert ecb.SERIES_ID in observacion.observation_id
    assert parse_qs(url.query) == {
        "endPeriod": [DOMINGO.isoformat()],
        "lastNObservations": ["1"],
        "format": ["csvdata"],
    }
    assert timeout == 2


def test_domingo_sin_observacion_previa_indica_fx_ausente(monkeypatch):
    simular_csv(monkeypatch, (LUNES, "1.20"))
    assert ecb.ECBFXProvider().get_rate("EUR", "USD", DOMINGO) is None


def test_par_inverso_no_se_convierte_en_el_adaptador(monkeypatch):
    peticiones = simular_csv(monkeypatch, (VIERNES, "1.10"))
    assert ecb.ECBFXProvider().get_rate("USD", "EUR", DOMINGO) is None
    assert peticiones == []


@pytest.mark.parametrize("codigo", [404, 429, 503])
def test_distingue_ausencia_de_datos_de_errores_http(monkeypatch, codigo):
    def abrir(peticion, *, timeout):
        raise HTTPError(peticion.full_url, codigo, "Respuesta simulada", None, BytesIO())

    monkeypatch.setattr(ecb, "urlopen", abrir)
    if codigo == 404:
        assert ecb.ECBFXProvider().get_rate("EUR", "USD", DOMINGO) is None
    else:
        with pytest.raises(HTTPError) as error:
            ecb.ECBFXProvider().get_rate("EUR", "USD", DOMINGO)
        assert error.value.code == codigo


@pytest.mark.parametrize("tasa", ["0", "NaN", "invalida"])
def test_rechaza_una_tasa_invalida(monkeypatch, tasa):
    simular_csv(monkeypatch, (VIERNES, tasa))
    with pytest.raises(ValueError, match="tasa inválida"):
        ecb.ECBFXProvider().get_rate("EUR", "USD", DOMINGO)
