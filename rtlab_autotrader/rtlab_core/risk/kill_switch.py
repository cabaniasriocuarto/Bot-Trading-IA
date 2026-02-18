from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class KillState:
    triggered: bool = False
    reason: str | None = None
    triggered_at: datetime | None = None
    manual_reset_required: bool = True


class KillSwitch:
    def __init__(self) -> None:
        self.state = KillState()

    def trigger(self, reason: str) -> KillState:
        if not self.state.triggered:
            self.state.triggered = True
            self.state.reason = reason
            self.state.triggered_at = datetime.now(timezone.utc)
        return self.state

    def reset(self) -> KillState:
        self.state = KillState()
        return self.state

    def is_triggered(self) -> bool:
        return self.state.triggered
