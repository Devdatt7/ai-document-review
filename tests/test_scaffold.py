import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient

import checks, claims, db, ingest, llm, models, pipeline, retrieval, scoring, verify  # noqa: F401,E401
from main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_models_build():
    assert models.DocumentResult().status == "REVIEW"
