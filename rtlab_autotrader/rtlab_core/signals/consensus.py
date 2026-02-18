from __future__ import annotations

from rtlab_core.types import CheckResult


def consensus(checks: dict[str, bool]) -> CheckResult:
    failed = [name for name, passed in checks.items() if not passed]
    return CheckResult(ok=not failed, failed_checks=failed)
