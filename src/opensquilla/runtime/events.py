"""Runtime event DTOs shared by engine and adapter stream wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class RunHeartbeatEvent:
    kind: Literal["run_heartbeat"] = field(default="run_heartbeat", init=False)
    phase: str = "agent"
    elapsed_ms: int = 0
    idle_ms: int = 0
    message: str = ""


__all__ = ["RunHeartbeatEvent"]
