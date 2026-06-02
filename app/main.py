from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.config import get_settings
from app.devin import (
    DevinClient,
    extract_acu_consumed,
    extract_pr_url,
    extract_session_id,
    extract_session_url,
    normalize_status,
)
from app.prompts import ISSUE_TITLES, build_devin_prompt
from app.storage import TaskStore


settings = get_settings()
store = TaskStore(settings.database_path)
devin = DevinClient(settings)
app = FastAPI(title="OpsBridge", version="0.1.0")


class SimulateRequest(BaseModel):
    issue_number: int | None = None
    issue_title: str | None = None
    issue_url: str | None = None
    trigger_source: str = "manual-simulated-event"
    dry_run: bool | None = None


class MessageRequest(BaseModel):
    message: str


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "devin_configured": settings.devin_configured,
        "real_devin_calls_enabled": settings.devin_enable_real_calls,
        "superset_repo": settings.superset_repo,
    }


@app.post("/api/simulate")
async def simulate_event(request: SimulateRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    issue_number = request.issue_number or settings.default_issue_number
    issue_title = request.issue_title or ISSUE_TITLES.get(issue_number, "GitHub remediation issue")
    issue_url = request.issue_url or f"{settings.superset_repo_url}/issues/{issue_number}"
    prompt = build_devin_prompt(settings.superset_repo_url, issue_number, issue_title)
    event_payload = request.model_dump()
    dry_run = request.dry_run if request.dry_run is not None else not settings.devin_enable_real_calls

    task = store.create_task(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        trigger_source=request.trigger_source,
        acu_limit=settings.devin_max_acu_limit,
        prompt=prompt,
        event_payload=event_payload,
    )

    if dry_run:
        payload = devin.build_session_payload(prompt=prompt, issue_number=issue_number)
        task = store.update_task(
            task.id,
            status="dry_run",
            status_detail="session payload prepared",
            error="Dry run only. Set DEVIN_ENABLE_REAL_CALLS=true and pass dry_run=false to create a Devin session.",
            event_payload={**event_payload, "devin_session_payload": payload},
        )
    else:
        background_tasks.add_task(start_devin_session, task.id)

    return {"task": task.to_dict(), "dashboard_url": "/dashboard"}


@app.get("/api/tasks")
def list_tasks() -> dict[str, Any]:
    return {"metrics": store.metrics(), "tasks": [task.to_dict() for task in store.list_tasks()]}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int) -> dict[str, Any]:
    try:
        return {"task": store.get_task(task_id).to_dict()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/sync")
async def sync_task(task_id: int) -> dict[str, Any]:
    try:
        task = store.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not task.devin_session_id:
        raise HTTPException(status_code=400, detail="Task does not have a Devin session yet.")
    updated = await refresh_devin_session(task.id, task.devin_session_id)
    return {"task": updated.to_dict()}


@app.post("/api/tasks/{task_id}/message")
async def send_task_message(task_id: int, request: MessageRequest) -> dict[str, Any]:
    try:
        task = store.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not task.devin_session_id:
        raise HTTPException(status_code=400, detail="Task does not have a Devin session yet.")
    payload = await devin.send_message(task.devin_session_id, request.message)
    updated = store.update_task(
        task.id,
        status=normalize_status(payload),
        status_detail=payload.get("status_detail"),
        devin_session_url=extract_session_url(payload) or task.devin_session_url,
        pr_url=extract_pr_url(payload) or task.pr_url,
        acu_consumed=extract_acu_consumed(payload),
    )
    return {"task": updated.to_dict()}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    metrics = store.metrics()
    tasks = store.list_tasks()
    rows = "\n".join(
        f"""
        <tr>
          <td>#{task.id}</td>
          <td><a href="{task.issue_url}">Issue #{task.issue_number}</a></td>
          <td><span class="status {task.status}">{task.status}</span><br><small>{task.status_detail or ""}</small></td>
          <td>{task.trigger_source}</td>
          <td>{link(task.devin_session_url, "session")}</td>
          <td>{link(task.pr_url, "PR")}</td>
          <td>{task.acu_consumed if task.acu_consumed is not None else "-"} / {task.acu_limit}</td>
          <td>{task.updated_at}</td>
        </tr>
        """
        for task in tasks
    ) or "<tr><td colspan='8'>No tasks yet. Trigger one with POST /api/simulate.</td></tr>"

    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>OpsBridge Dashboard</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
        header {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; }}
        h1 {{ margin: 0; font-size: 28px; }}
        .subtitle {{ color: #4b5563; margin-top: 8px; }}
        .metrics {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; margin: 28px 0; }}
        .metric {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 14px; background: #f9fafb; }}
        .metric strong {{ display: block; font-size: 24px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ text-align: left; border-bottom: 1px solid #e5e7eb; padding: 10px; vertical-align: top; }}
        th {{ background: #f3f4f6; }}
        .status {{ padding: 3px 8px; border-radius: 999px; background: #e5e7eb; }}
        .completed {{ background: #dcfce7; color: #166534; }}
        .failed, .blocked {{ background: #fee2e2; color: #991b1b; }}
        .running {{ background: #dbeafe; color: #1e40af; }}
        .dry_run {{ background: #fef3c7; color: #92400e; }}
        code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
      </style>
    </head>
    <body>
      <header>
        <div>
          <h1>OpsBridge</h1>
          <div class="subtitle">Event-driven Devin remediation control plane for Superset maintenance issues.</div>
        </div>
        <div>Real Devin calls: <code>{settings.devin_enable_real_calls}</code></div>
      </header>
      <section class="metrics">
        <div class="metric"><strong>{metrics["total"]}</strong>Total tasks</div>
        <div class="metric"><strong>{metrics["completed"]}</strong>Completed</div>
        <div class="metric"><strong>{metrics["failed_or_blocked"]}</strong>Failed/blocked</div>
        <div class="metric"><strong>{metrics["prs_opened"]}</strong>PRs opened</div>
        <div class="metric"><strong>{metrics["acu_consumed"]:.2f}</strong>ACUs reported</div>
      </section>
      <table>
        <thead>
          <tr>
            <th>Task</th><th>Issue</th><th>Status</th><th>Trigger</th>
            <th>Devin</th><th>Output</th><th>ACUs</th><th>Updated</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </body>
    </html>
    """


async def start_devin_session(task_id: int) -> None:
    task = store.update_task(task_id, status="running")
    start = time.monotonic()
    try:
        payload = await devin.create_session(prompt=task.prompt, issue_number=task.issue_number)
        session_id = extract_session_id(payload)
        session_url = extract_session_url(payload)
        if not session_id:
            store.update_task(task.id, status="blocked", error=f"Devin response did not include a session id: {payload}")
            return
        task = store.update_task(
            task.id,
            status="running",
            devin_session_id=session_id,
            devin_session_url=session_url,
            elapsed_seconds=round(time.monotonic() - start, 2),
        )
        await refresh_devin_session(task.id, session_id)
    except httpx.HTTPError as exc:
        store.update_task(task.id, status="failed", error=str(exc), elapsed_seconds=round(time.monotonic() - start, 2))


async def refresh_devin_session(task_id: int, session_id: str):
    task = store.get_task(task_id)
    started = time.monotonic()
    try:
        payload = await devin.get_session(session_id)
        return store.update_task(
            task.id,
            status=normalize_status(payload),
            status_detail=payload.get("status_detail"),
            devin_session_url=extract_session_url(payload) or task.devin_session_url,
            pr_url=extract_pr_url(payload) or task.pr_url,
            acu_consumed=extract_acu_consumed(payload),
            elapsed_seconds=(task.elapsed_seconds or 0) + round(time.monotonic() - started, 2),
        )
    except httpx.HTTPError as exc:
        return store.update_task(task.id, status="failed", error=str(exc))


def link(url: str | None, label: str) -> str:
    return f'<a href="{url}">{label}</a>' if url else "-"
