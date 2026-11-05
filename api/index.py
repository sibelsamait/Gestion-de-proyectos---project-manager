"""Entrada WSGI para Vercel."""

from app import create_app

app = create_app()
