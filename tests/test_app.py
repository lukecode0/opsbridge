from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app, settings


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


def test_github_webhook_labeled_event_creates_dry_run_task() -> None:
    client = TestClient(app)
    secret = webhook_secret()
    payload = {
        "action": "labeled",
        "label": {"name": "devin-remediate"},
        "repository": {"full_name": "lukecode0/superset"},
        "issue": {
            "number": 2,
            "title": "Run focused Ruff/code-quality cleanup",
            "html_url": "https://github.com/lukecode0/superset/issues/2",
        },
    }

    response = client.post(
        "/api/github/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": signature(payload, secret),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["task"]["status"] == "dry_run"
    assert body["task"]["trigger_source"] == "github-issue-label-webhook"


def test_github_webhook_ignores_other_labels() -> None:
    client = TestClient(app)
    secret = webhook_secret()
    payload = {
        "action": "labeled",
        "label": {"name": "not-devin"},
        "repository": {"full_name": "lukecode0/superset"},
        "issue": {"number": 2, "title": "Other", "html_url": "https://github.com/lukecode0/superset/issues/2"},
    }
    response = client.post(
        "/api/github/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-2",
            "X-Hub-Signature-256": signature(payload, secret),
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is False


def test_github_webhook_rejects_invalid_signature() -> None:
    client = TestClient(app)
    payload = {"action": "labeled"}

    response = client.post(
        "/api/github/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-3",
            "X-Hub-Signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 401


def signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def webhook_secret() -> str:
    assert settings.github_webhook_secret
    return settings.github_webhook_secret
