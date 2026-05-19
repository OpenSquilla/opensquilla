"""Compatibility re-export for shared runtime stream wrappers."""

from __future__ import annotations

from opensquilla.runtime.stream_wrappers import (
    heartbeat_stream,
    idle_timeout_stream,
    repair_json_stream,
    trim_tool_names_stream,
    wrap_stream,
)

__all__ = [
    "heartbeat_stream",
    "idle_timeout_stream",
    "repair_json_stream",
    "trim_tool_names_stream",
    "wrap_stream",
]
