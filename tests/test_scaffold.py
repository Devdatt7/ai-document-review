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


def test_cors_allowed_origins():
    from starlette.middleware.cors import CORSMiddleware

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    origins = [*cors.kwargs["allow_origins"], "http://localhost:5173",
               "http://127.0.0.1:5173"]
    client = TestClient(app)
    for origin in origins:
        response = client.options("/analyze", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert client.get("/health", headers={"Origin": origin}).headers[
            "access-control-allow-origin"
        ] == origin


def test_cors_rejects_untrusted_origin():
    response = TestClient(app).options("/analyze", headers={
        "Origin": "https://untrusted.example",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
