from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_simulate_defaults_to_dry_run() -> None:
    client = TestClient(app)
    response = client.post("/api/simulate", json={"issue_number": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "dry_run"
    assert payload["task"]["issue_number"] == 3
    assert "devin_session_payload" in payload["task"]["event_payload"]


def test_dashboard_renders() -> None:
    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "OpsBridge" in response.text
