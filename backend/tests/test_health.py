"""Health endpoint: reports database readiness without raising."""

from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient


def test_health_reports_ok_when_database_is_reachable(migrated_database: None) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"


def test_health_is_degraded_when_database_query_fails(monkeypatch) -> None:
    import app.api.health as health_module

    monkeypatch.setattr(
        health_module, "check_database", lambda: (False, "OperationalError: boom")
    )

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "error"
    assert "boom" in body["detail"]
