"""Compatibility entrypoint for FastAPI Cloud auto-detection.

FastAPI Cloud starts from the application directory and looks for a
top-level ``main.py`` by default.  The actual application remains in
``app.main``; this module simply exposes the same FastAPI instance.
"""

from app.main import app

__all__ = ["app"]
