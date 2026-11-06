"""Pruebas aisladas del servicio multidivisa."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from test_auth_and_rbac import login, register

from app.extensions import db
from app.models import ExchangeRate
from app.services.currency import (
    MindicadorProvider,
    RateError,
    RateUnavailableError,
    convert,
    format_money,
    get_rate,
    refresh_rates,
)


class FakeResponse:
    """Respuesta HTTP mínima para probar el proveedor sin Internet."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def insert_rate(indicator: str, rate_date: date, value: str) -> None:
    db.session.add(
        ExchangeRate(
            indicator=indicator,
            rate_date=rate_date,
            value=Decimal(value),
            source="test",
            fetched_at=datetime.now(UTC),
        )
    )
    db.session.commit()


def test_conversion_rounding_and_format(app):
    with app.app_context():
        insert_rate("USD", date(2026, 11, 5), "950.123456")
        result = convert(Decimal(1000), "USD", date(2026, 11, 5))
        assert result.amount == Decimal("1.05")
        assert result.rate_used == Decimal("950.123456")
        assert format_money(result.amount, "USD") == "US$ 1,05"
        assert format_money(Decimal("1234.5"), "CLP") == "$1.235"


def test_uses_previous_business_day_and_marks_stale(app):
    with app.app_context():
        insert_rate("UF", date(2026, 11, 2), "40000")
        result = convert(Decimal(80000), "UF", date(2026, 11, 5))
        assert result.amount == Decimal("2.00")
        assert result.rate_date == date(2026, 11, 2)
        assert result.is_stale is False


def test_rate_is_stale_after_three_days(app):
    with app.app_context():
        insert_rate("USD", date(2026, 11, 1), "900")
        rate = get_rate("USD", date(2026, 11, 5))
        assert rate.is_stale is True


def test_missing_rate_is_explicit(app):
    with app.app_context(), pytest.raises(RateUnavailableError):
        convert(Decimal(100), "UF", date(2026, 11, 5))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"serie":[]}',
        b'{"serie":[{"fecha":"2026-11-05T03:00:00.000Z","valor":-1}]}',
        b'{"serie":[{"fecha":"2026-11-05T03:00:00.000Z","valor":"texto"}]}',
        b'{"serie":[{"fecha":"no-es-fecha","valor":1}]}',
    ],
)
def test_provider_rejects_invalid_responses(app, payload):
    with app.app_context():
        provider = MindicadorProvider(
            base_url="https://mindicador.cl/api",
            opener=lambda *_args, **_kwargs: FakeResponse(payload),
        )
        with pytest.raises(RateError):
            provider.fetch("UF")


def test_provider_parses_mindicador_series(app):
    with app.app_context():
        provider = MindicadorProvider(
            base_url="https://mindicador.cl/api",
            opener=lambda *_args, **_kwargs: FakeResponse(
                b'{"serie":[{"fecha":"2026-11-05T03:00:00.000Z","valor":40000.25}]}'
            ),
        )
        assert provider.fetch("UF") == [(date(2026, 11, 5), Decimal("40000.25"))]


def test_refresh_is_idempotent_and_preserves_data_on_failure(app):
    class Provider:
        source = "mock"

        def fetch(self, indicator):
            if indicator == "USD":
                raise RateError("caída")
            return [(date(2026, 11, 5), Decimal(40000))]

    with app.app_context():
        assert refresh_rates(Provider()) == {"UF": 1, "USD": 0}
        assert refresh_rates(Provider()) == {"UF": 1, "USD": 0}
        assert db.session.query(ExchangeRate).count() == 1
        assert get_rate("UF", date(2026, 11, 5)).value == Decimal("40000.000000")


def test_currency_preference_and_cron_authentication(client, app):
    register(client, "currency@example.com")
    login(client, "currency@example.com")
    response = client.post("/settings/currency", data={"currency": "USD"})
    assert response.status_code == 302
    with client.session_transaction() as current_session:
        assert current_session["currency"] == "USD"

    app.config["CRON_SECRET"] = "cron-test-secret"
    assert client.get("/internal/refresh-rates").status_code == 401
    assert client.get(
        "/internal/refresh-rates",
        headers={"Authorization": "wrong"},
    ).status_code == 401
    with patch("app.blueprints.currency.refresh_rates", return_value={"UF": 1, "USD": 1}):
        response = client.get(
            "/internal/refresh-rates",
            headers={"Authorization": "Bearer cron-test-secret"},
        )
    assert response.status_code == 200
    assert response.get_json()["updated"] == {"UF": 1, "USD": 1}
