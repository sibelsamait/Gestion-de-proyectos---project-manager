"""Proveedor y servicio de tasas de cambio, con CLP como moneda base."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import ExchangeRate

LOGGER = logging.getLogger(__name__)
SUPPORTED_CURRENCIES = frozenset({"CLP", "UF", "USD"})
INDICATORS = frozenset({"UF", "USD"})
SOURCE_NAME = "mindicador.cl"
RATE_TIMEOUT_SECONDS = 5
MAX_RETRIES = 2
ONE = Decimal(1)


class RateError(RuntimeError):
    """Error controlado al consultar o validar una tasa."""


class RateUnavailableError(RateError):
    """No existe una tasa utilizable para la fecha solicitada."""


@dataclass(frozen=True)
class RateValue:
    """Tasa resuelta y metadatos de antigüedad."""

    indicator: str
    value: Decimal
    rate_date: date
    is_stale: bool


@dataclass(frozen=True)
class Conversion:
    """Resultado de una conversión monetaria."""

    amount: Decimal
    currency: str
    rate_used: Decimal
    rate_date: date
    is_stale: bool


class RateProvider(Protocol):
    """Interfaz para proveedores intercambiables de indicadores."""

    source: str

    def fetch(self, indicator: str) -> list[tuple[date, Decimal]]:
        """Obtiene el histórico disponible de un indicador."""


class MindicadorProvider:
    """Adaptador validado para la API pública de mindicador.cl."""

    source = SOURCE_NAME

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = RATE_TIMEOUT_SECONDS,
        opener: Any = urlopen,
    ) -> None:
        self.base_url = (base_url or current_app.config["RATES_API_URL"]).rstrip("/")
        if not self.base_url.startswith("https://"):
            raise RateError("La URL de tasas debe usar HTTPS.")
        self.timeout = min(timeout, RATE_TIMEOUT_SECONDS)
        self._opener = opener

    def fetch(self, indicator: str) -> list[tuple[date, Decimal]]:
        """Descarga y valida la serie de UF o dólar observado."""
        normalized = indicator.upper()
        if normalized not in INDICATORS:
            raise RateError(f"Indicador no permitido: {indicator}")
        endpoint = "uf" if normalized == "UF" else "dolar"
        request = Request(
            f"{self.base_url}/{endpoint}",
            headers={"Accept": "application/json", "User-Agent": "project-manager/1.0"},
        )
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return self._parse_series(payload, normalized)
            except (OSError, URLError, TimeoutError, ValueError, RateError) as error:
                last_error = error
                if attempt < MAX_RETRIES:
                    time.sleep(0.1 * (attempt + 1))
        raise RateError(f"No se pudo obtener {normalized} desde mindicador.cl.") from last_error

    @staticmethod
    def _parse_series(payload: Any, indicator: str) -> list[tuple[date, Decimal]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("serie"), list):
            raise RateError("La respuesta de tasas no contiene una serie válida.")
        result: list[tuple[date, Decimal]] = []
        for item in payload["serie"]:
            if not isinstance(item, dict) or not isinstance(item.get("fecha"), str):
                raise RateError("La respuesta contiene una fecha inválida.")
            raw_value = item.get("valor")
            if isinstance(raw_value, bool) or raw_value is None:
                raise RateError("La respuesta contiene un valor inválido.")
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError) as error:
                raise RateError("La respuesta contiene un valor no numérico.") from error
            if not value.is_finite() or value <= 0:
                raise RateError("La respuesta contiene una tasa no positiva.")
            try:
                rate_date = datetime.fromisoformat(item["fecha"]).date()
            except ValueError as error:
                raise RateError("La respuesta contiene una fecha no ISO 8601.") from error
            result.append((rate_date, value))
        if not result:
            raise RateError(f"La serie de {indicator} está vacía.")
        return result


def _validate_currency(currency: str) -> str:
    normalized = currency.upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError("Moneda no soportada. Usa CLP, UF o USD.")
    return normalized


def validate_currency(currency: str | None) -> str:
    """Valida una moneda externa y usa CLP cuando no se especifica."""
    return _validate_currency(currency or "CLP")


def currency_context(
    currency: str = "CLP",
    on_date: date | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    """Devuelve tasa y metadatos para una respuesta o plantilla."""
    normalized = validate_currency(currency)
    requested_date = on_date or date.today()
    if normalized == "CLP":
        return {
            "currency": normalized,
            "rate_used": ONE,
            "rate_date": requested_date.isoformat(),
            "rate_date_display": requested_date.strftime("%d-%m-%Y"),
            "is_stale": False,
        }
    rate = get_rate(normalized, requested_date, session)
    return {
        "currency": normalized,
        "rate_used": rate.value,
        "rate_date": rate.rate_date.isoformat(),
        "rate_date_display": rate.rate_date.strftime("%d-%m-%Y"),
        "is_stale": rate.is_stale,
    }


def convert_with_context(amount_clp: Decimal | int | str, context: dict[str, Any]) -> Decimal:
    """Convierte usando una tasa ya resuelta para evitar consultas repetidas."""
    amount = Decimal(str(amount_clp))
    if context["currency"] == "CLP":
        return amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return (amount / context["rate_used"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_rate(indicator: str, on_date: date | None = None, session: Session | None = None) -> RateValue:
    """Obtiene la tasa exacta o la última anterior disponible."""
    normalized = indicator.upper()
    if normalized not in INDICATORS:
        raise ValueError("Indicador no soportado. Usa UF o USD.")
    requested_date = on_date or date.today()
    query = select(ExchangeRate).where(
        ExchangeRate.indicator == normalized,
        ExchangeRate.rate_date <= requested_date,
    ).order_by(ExchangeRate.rate_date.desc())
    row = (session or _db_session()).scalar(query)
    if row is None:
        raise RateUnavailableError(f"No hay tasa {normalized} para {requested_date.isoformat()}.")
    return RateValue(
        indicator=normalized,
        value=Decimal(row.value),
        rate_date=row.rate_date,
        is_stale=(requested_date - row.rate_date) > timedelta(days=3),
    )


def _db_session() -> Session:
    from ..extensions import db

    return db.session


def convert(
    amount_clp: Decimal | int | str,
    to_currency: str,
    on_date: date | None = None,
    session: Session | None = None,
) -> Conversion:
    """Convierte CLP sin persistir el monto convertido."""
    currency = _validate_currency(to_currency)
    amount = Decimal(str(amount_clp))
    if not amount.is_finite():
        raise ValueError("El monto debe ser finito.")
    if currency == "CLP":
        return Conversion(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP), currency, ONE, on_date or date.today(), False)
    rate = get_rate(currency, on_date, session)
    converted = (amount / rate.value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Conversion(converted, currency, rate.value, rate.rate_date, rate.is_stale)


def format_money(amount: Decimal | int | str, currency: str = "CLP") -> str:
    """Formatea un monto con separadores es-CL y redondeo financiero."""
    normalized = _validate_currency(currency)
    decimals = 0 if normalized == "CLP" else 2
    quantized = Decimal(str(amount)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    text = f"{quantized:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    prefix = {"CLP": "$", "UF": "UF ", "USD": "US$ "}[normalized]
    return f"{prefix}{text}"


def refresh_rates(
    provider: RateProvider | None = None,
    session: Session | None = None,
    since: date | None = None,
) -> dict[str, int]:
    """Actualiza idempotentemente las series disponibles, conservando datos ante fallos."""
    db_session = session or _db_session()
    rate_provider = provider or MindicadorProvider()
    counts: dict[str, int] = {}
    for indicator in sorted(INDICATORS):
        try:
            series = rate_provider.fetch(indicator)
            if since is not None:
                series = [(rate_date, value) for rate_date, value in series if rate_date >= since]
            for rate_date, value in series:
                row = db_session.scalar(
                    select(ExchangeRate).where(
                        ExchangeRate.indicator == indicator,
                        ExchangeRate.rate_date == rate_date,
                    )
                )
                if row is None:
                    db_session.add(
                        ExchangeRate(
                            indicator=indicator,
                            rate_date=rate_date,
                            value=value,
                            source=rate_provider.source,
                            fetched_at=datetime.now(UTC),
                        )
                    )
                else:
                    row.value = value
                    row.source = rate_provider.source
                    row.fetched_at = datetime.now(UTC)
            db_session.commit()
            counts[indicator] = len(series)
        except (RateError, SQLAlchemyError):
            db_session.rollback()
            LOGGER.exception("No se pudo actualizar la tasa %s; se conserva el histórico.", indicator)
            counts[indicator] = 0
    return counts


def register_cli(app: Any) -> None:
    """Registra comandos Flask para refrescar tasas."""
    import click

    @app.cli.command("refresh-rates")
    def refresh_rates_command() -> None:
        """Actualiza UF y dólar desde mindicador.cl."""
        counts = refresh_rates()
        click.echo(json.dumps(counts, ensure_ascii=False))

    @app.cli.command("backfill-rates")
    @click.option("--days", default=90, type=click.IntRange(min=1, max=3650), show_default=True)
    def backfill_rates_command(days: int) -> None:
        """Carga el histórico disponible hasta el límite solicitado."""
        counts = refresh_rates(since=date.today() - timedelta(days=days - 1))
        click.echo(json.dumps(counts, ensure_ascii=False))
