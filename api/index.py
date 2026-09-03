"""Vercel entry point: exposes the FastAPI app as one Python serverless function.

`vercel.json` rewrites /v1/*, /health, /docs and /openapi.json to this function, and the
app sees the original path, so nothing in `backend/` knows it is running on Vercel.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401  (Vercel looks for a module-level `app`)
