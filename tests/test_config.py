from __future__ import annotations

from app.config import _env


def test_env_strips_accidental_key_prefix(monkeypatch) -> None:
    monkeypatch.setenv("DEVIN_ORG_ID", "DEVIN_ORG_ID=org-example")

    assert _env("DEVIN_ORG_ID") == "org-example"
