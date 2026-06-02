from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    devin_org_id: str
    devin_api_key: str
    devin_api_base_url: str
    devin_enable_real_calls: bool
    devin_max_acu_limit: int
    superset_repo: str
    superset_repo_url: str
    default_issue_number: int
    database_path: str
    github_webhook_secret: str

    @property
    def devin_configured(self) -> bool:
        return bool(self.devin_org_id and self.devin_api_key)


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        devin_org_id=os.getenv("DEVIN_ORG_ID", ""),
        devin_api_key=os.getenv("DEVIN_API_KEY", ""),
        devin_api_base_url=os.getenv("DEVIN_API_BASE_URL", "https://api.devin.ai").rstrip("/"),
        devin_enable_real_calls=_bool_env("DEVIN_ENABLE_REAL_CALLS", False),
        devin_max_acu_limit=int(os.getenv("DEVIN_MAX_ACU_LIMIT", "2")),
        superset_repo=os.getenv("SUPERSET_REPO", "lukecode0/superset"),
        superset_repo_url=os.getenv("SUPERSET_REPO_URL", "https://github.com/lukecode0/superset"),
        default_issue_number=int(os.getenv("DEFAULT_ISSUE_NUMBER", "3")),
        database_path=os.getenv("DATABASE_PATH", "opsbridge.db"),
        github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
    )
