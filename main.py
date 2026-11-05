"""Vercel entrypoint: Vercel auto-detects a FastAPI `app` exported from main.py."""
from app.api import app  # noqa: F401
