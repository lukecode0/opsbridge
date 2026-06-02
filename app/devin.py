from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import Settings


class DevinClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.devin_api_key}",
            "Content-Type": "application/json",
        }

    def build_session_payload(self, *, prompt: str, issue_number: int) -> dict[str, Any]:
        return {
            "prompt": prompt,
            "title": f"Superset issue #{issue_number} remediation",
            "repos": [self.settings.superset_repo_url],
            "tags": ["opsbridge", "superset", f"issue-{issue_number}"],
            "max_acu_limit": self.settings.devin_max_acu_limit,
        }

    async def create_session(self, *, prompt: str, issue_number: int) -> dict[str, Any]:
        payload = self.build_session_payload(prompt=prompt, issue_number=issue_number)
        url = f"{self.settings.devin_api_base_url}/v3/organizations/{self.settings.devin_org_id}/sessions"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        url = f"{self.settings.devin_api_base_url}/v3/organizations/{self.settings.devin_org_id}/sessions/{session_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        devin_id = session_id if session_id.startswith("devin-") else f"devin-{session_id}"
        url = f"{self.settings.devin_api_base_url}/v3/organizations/{self.settings.devin_org_id}/sessions/{devin_id}/messages"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self.headers, json={"message": message})
            response.raise_for_status()
            return response.json()


def extract_session_id(payload: dict[str, Any]) -> str | None:
    for key in ("session_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def extract_session_url(payload: dict[str, Any]) -> str | None:
    for key in ("session_url", "url", "app_url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def extract_pr_url(payload: dict[str, Any]) -> str | None:
    for key in ("pull_request_url", "pr_url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    pr_urls = payload.get("pull_request_urls") or payload.get("pr_urls")
    if isinstance(pr_urls, list) and pr_urls:
        first = pr_urls[0]
        return first if isinstance(first, str) else None
    pull_requests = payload.get("pull_requests")
    if isinstance(pull_requests, list):
        for pull_request in pull_requests:
            if isinstance(pull_request, dict) and isinstance(pull_request.get("pr_url"), str):
                return pull_request["pr_url"]
    text = str(payload)
    match = re.search(r"https://github\.com/[^\\s'\"]+/pull/\d+", text)
    return match.group(0) if match else None


def normalize_status(payload: dict[str, Any]) -> str:
    raw_status = str(payload.get("status") or payload.get("state") or "").lower()
    status_detail = str(payload.get("status_detail") or "").lower()
    if raw_status == "exit" and status_detail == "finished":
        return "completed"
    if raw_status in {"finished", "completed", "succeeded", "success"}:
        return "completed"
    if raw_status in {"error", "failed", "failure"}:
        return "failed"
    if raw_status in {"blocked", "suspended"}:
        return "blocked"
    if raw_status in {"running", "starting", "queued"}:
        return "running"
    return "running" if raw_status else "unknown"


def extract_acu_consumed(payload: dict[str, Any]) -> float | None:
    for key in ("acu_consumed", "acus_consumed", "ac_us_consumed"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    insights = payload.get("insights")
    if isinstance(insights, dict):
        value = insights.get("acu_consumed") or insights.get("acus_consumed")
        if isinstance(value, (int, float)):
            return float(value)
    return None
