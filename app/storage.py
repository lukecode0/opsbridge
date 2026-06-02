from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    id: int
    issue_number: int
    issue_title: str
    issue_url: str
    status: str
    status_detail: str | None
    trigger_source: str
    devin_session_id: str | None
    devin_session_url: str | None
    pr_url: str | None
    acu_limit: int
    acu_consumed: float | None
    elapsed_seconds: float | None
    error: str | None
    prompt: str
    event_payload: dict[str, Any]
    created_at: str
    updated_at: str
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_number INTEGER NOT NULL,
                    issue_title TEXT NOT NULL,
                    issue_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_detail TEXT,
                    trigger_source TEXT NOT NULL,
                    devin_session_id TEXT,
                    devin_session_url TEXT,
                    pr_url TEXT,
                    acu_limit INTEGER NOT NULL,
                    acu_consumed REAL,
                    elapsed_seconds REAL,
                    error TEXT,
                    prompt TEXT NOT NULL,
                    event_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            if "status_detail" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN status_detail TEXT")

    def create_task(
        self,
        *,
        issue_number: int,
        issue_title: str,
        issue_url: str,
        trigger_source: str,
        acu_limit: int,
        prompt: str,
        event_payload: dict[str, Any],
    ) -> Task:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    issue_number, issue_title, issue_url, status, trigger_source,
                    acu_limit, prompt, event_payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue_number,
                    issue_title,
                    issue_url,
                    "queued",
                    trigger_source,
                    acu_limit,
                    prompt,
                    json.dumps(event_payload, sort_keys=True),
                    now,
                    now,
                ),
            )
            task_id = int(cursor.lastrowid)
        return self.get_task(task_id)

    def update_task(self, task_id: int, **fields: Any) -> Task:
        if not fields:
            return self.get_task(task_id)
        fields["updated_at"] = utc_now()
        if fields.get("status") in {"completed", "failed", "blocked"} and "completed_at" not in fields:
            fields["completed_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [json.dumps(value) if key == "event_payload" else value for key, value in fields.items()]
        with self.connect() as conn:
            conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", [*values, task_id])
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> Task:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} not found")
        return self._from_row(row)

    def list_tasks(self) -> list[Task]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def metrics(self) -> dict[str, Any]:
        tasks = self.list_tasks()
        by_status: dict[str, int] = {}
        for task in tasks:
            by_status[task.status] = by_status.get(task.status, 0) + 1
        completed = [task for task in tasks if task.status == "completed"]
        failed = [task for task in tasks if task.status in {"failed", "blocked"}]
        return {
            "total": len(tasks),
            "by_status": by_status,
            "completed": len(completed),
            "failed_or_blocked": len(failed),
            "prs_opened": sum(1 for task in tasks if task.pr_url),
            "acu_consumed": sum(task.acu_consumed or 0 for task in tasks),
        }

    def _from_row(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            issue_number=row["issue_number"],
            issue_title=row["issue_title"],
            issue_url=row["issue_url"],
            status=row["status"],
            status_detail=row["status_detail"],
            trigger_source=row["trigger_source"],
            devin_session_id=row["devin_session_id"],
            devin_session_url=row["devin_session_url"],
            pr_url=row["pr_url"],
            acu_limit=row["acu_limit"],
            acu_consumed=row["acu_consumed"],
            elapsed_seconds=row["elapsed_seconds"],
            error=row["error"],
            prompt=row["prompt"],
            event_payload=json.loads(row["event_payload"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )
