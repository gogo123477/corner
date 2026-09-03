import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.db import init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Corner API",
    version="0.1.0",
    description="Cross-domain personal coach. Deterministic engine, LLM for language only.",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True}
