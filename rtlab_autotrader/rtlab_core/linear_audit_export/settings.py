from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Scope = Literal["workspace", "delivery", "issues", "audit", "attachments", "customers", "all"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "linear_export"


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    return float(raw)


@dataclass(slots=True)
class ExporterSettings:
    base_url: str
    output_dir: Path
    include_attachments: bool
    include_audit: bool
    include_customers: bool
    page_size: int
    timeout_seconds: float
    retry_max: int
    resume: bool
    max_issues: int
    log_level: str
    scope: Scope
    api_key: str
    access_token: str
    public_file_urls_expire_in: int | None = None
    hash_files: bool = False
    test_limit: int = 0

    @classmethod
    def from_env(
        cls,
        *,
        scope: Scope = "all",
        output_dir: Path | None = None,
        max_issues: int | None = None,
        include_attachments: bool | None = None,
        include_audit: bool | None = None,
        include_customers: bool | None = None,
        page_size: int | None = None,
        timeout_seconds: float | None = None,
        retry_max: int | None = None,
        resume: bool | None = None,
        log_level: str | None = None,
        hash_files: bool | None = None,
        test_limit: int | None = None,
    ) -> "ExporterSettings":
        effective_output = output_dir or Path(os.getenv("LINEAR_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
        effective_page_size = max(1, min(int(page_size or _env_int("LINEAR_PAGE_SIZE", 50)), 100))
        effective_timeout = float(timeout_seconds or _env_float("LINEAR_TIMEOUT_SECONDS", 60.0))
        effective_retry_max = max(0, int(retry_max or _env_int("LINEAR_RETRY_MAX", 5)))
        effective_resume = bool(resume if resume is not None else _env_bool("LINEAR_RESUME", True))
        effective_max_issues = int(max_issues if max_issues is not None else _env_int("LINEAR_MAX_ISSUES", 0))
        effective_test_limit = int(test_limit if test_limit is not None else _env_int("LINEAR_TEST_LIMIT", 0))
        expire_raw = str(os.getenv("LINEAR_PUBLIC_FILE_URLS_EXPIRE_IN", "")).strip()
        public_file_urls_expire_in = int(expire_raw) if expire_raw else None
        return cls(
            base_url=str(os.getenv("LINEAR_BASE_URL", "https://api.linear.app/graphql")).strip(),
            output_dir=effective_output,
            include_attachments=bool(
                include_attachments if include_attachments is not None else _env_bool("LINEAR_INCLUDE_ATTACHMENTS", True)
            ),
            include_audit=bool(include_audit if include_audit is not None else _env_bool("LINEAR_INCLUDE_AUDIT", True)),
            include_customers=bool(
                include_customers if include_customers is not None else _env_bool("LINEAR_INCLUDE_CUSTOMERS", True)
            ),
            page_size=effective_page_size,
            timeout_seconds=effective_timeout,
            retry_max=effective_retry_max,
            resume=effective_resume,
            max_issues=effective_max_issues,
            log_level=str(log_level or os.getenv("LINEAR_LOG_LEVEL", "INFO")).strip().upper() or "INFO",
            scope=scope,
            api_key=str(os.getenv("LINEAR_API_KEY", "")).strip(),
            access_token=str(os.getenv("LINEAR_ACCESS_TOKEN", "")).strip(),
            public_file_urls_expire_in=public_file_urls_expire_in,
            hash_files=bool(hash_files if hash_files is not None else _env_bool("LINEAR_HASH_FILES", False)),
            test_limit=effective_test_limit,
        )

    def auth_headers(self) -> dict[str, str]:
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        if self.api_key:
            return {"Authorization": self.api_key}
        return {}

    def require_auth(self) -> None:
        if self.auth_headers():
            return
        raise RuntimeError(
            "Falta credencial GraphQL de Linear. Configura LINEAR_API_KEY o LINEAR_ACCESS_TOKEN antes de correr snapshot."
        )

