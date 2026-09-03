import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.api.routes import router
from app.config import get_settings
from app.db import engine, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except (OperationalError, DBAPIError) as exc:  # keep /health reachable to explain why
        logging.getLogger("corner").error("database init failed: %s", exc)
    yield


app = FastAPI(
    title="Corner API",
    version="0.1.0",
    description="Cross-domain personal coach. Deterministic engine, LLM for language only.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(OperationalError)
@app.exception_handler(DBAPIError)
async def _db_error(_: Request, exc: Exception):
    hint = ""
    if engine.url.get_backend_name() == "sqlite" and os.environ.get("VERCEL"):
        hint = " CORNER_DATABASE_URL is not set, so the app fell back to SQLite, which cannot run on Vercel."
    return JSONResponse(503, {"detail": f"Database unavailable: {str(exc).splitlines()[0]}.{hint}"})


@app.get("/health")
def health():
    """Reports whether the database is reachable; 503 with the reason if not."""
    backend = engine.url.get_backend_name()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except (OperationalError, DBAPIError) as exc:
        hint = (
            " Set CORNER_DATABASE_URL to a Postgres URL."
            if backend == "sqlite" and os.environ.get("VERCEL")
            else ""
        )
        return JSONResponse(
            503, {"ok": False, "db": backend, "error": str(exc).splitlines()[0] + hint}
        )
    return {"ok": True, "db": backend}
