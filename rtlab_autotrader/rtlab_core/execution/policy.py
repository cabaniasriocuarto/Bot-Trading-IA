from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionPolicy:
    post_only: bool = True
    order_timeout_sec: int = 45
    max_requotes: int = 2


def should_requote(requote_count: int, policy: ExecutionPolicy) -> bool:
    return requote_count < policy.max_requotes
