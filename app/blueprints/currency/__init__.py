"""Preferencia de moneda y refresco interno de tasas."""

import hmac

from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for
from flask_login import login_required

from ...extensions import csrf
from ...services.currency import refresh_rates, validate_currency

currency_bp = Blueprint("currency", __name__)


@currency_bp.post("/settings/currency")
@login_required
def set_currency():
    """Guarda la moneda de presentación en la sesión actual."""
    try:
        currency = validate_currency(request.form.get("currency") or request.get_json(silent=True).get("currency"))
    except (AttributeError, TypeError, ValueError):
        return jsonify({"error": "Moneda no soportada. Usa CLP, UF o USD."}), 400
    session["currency"] = currency
    if request.accept_mimetypes.best == "application/json":
        return jsonify({"currency": currency})
    return redirect(request.referrer or url_for("projects.dashboard"))


@currency_bp.get("/internal/refresh-rates")
@csrf.exempt
def refresh_rates_endpoint():
    """Actualiza tasas solo cuando el secreto de cron coincide."""
    secret = current_app.config.get("CRON_SECRET", "")
    authorization = request.headers.get("Authorization", "")
    valid_authorization = (
        hmac.compare_digest(authorization, secret)
        or hmac.compare_digest(authorization, f"Bearer {secret}")
    ) if secret else False
    if not valid_authorization:
        return jsonify({"error": "No autorizado"}), 401
    counts = refresh_rates()
    return jsonify({"updated": counts})
