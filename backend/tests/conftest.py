import os

import pytest

SCRATCH = os.environ.get("CORNER_TEST_DIR", os.path.dirname(__file__))
os.environ["CORNER_DATABASE_URL"] = f"sqlite:///{SCRATCH}/test.db"
os.environ["CORNER_AUTH_MODE"] = "dev"
os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import models
    from app.db import engine
    from app.main import app

    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer dev:alice"
        yield c
