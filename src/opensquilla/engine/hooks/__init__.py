"""Engine-level hook protocols.

engine hook seam introduces three typed hook surfaces on the Agent + TurnRunner:

* :class:`TurnHook` — turn lifecycle events (``before_turn``, ``after_turn``,
  ``on_error``, ``on_event``).
* :class:`ToolHook` — tool dispatch surround (``before_tool``, ``after_tool``).
* :class:`CompactionHook` — compaction lifecycle (``before_compact``,
  ``after_compact``).

Default implementations in :mod:`opensquilla.engine.hooks.defaults` reproduce
the original direct behavior so registering an empty hook list is equivalent to
running the canonical code path.
"""

from __future__ import annotations

from opensquilla.engine.hooks.defaults import (
    DefaultMemoryFlushHook,
    DefaultTraceEmitterHook,
    DefaultTranscriptHook,
    NoopCompactionHook,
    NoopToolHook,
    NoopTurnHook,
    build_default_turn_hooks,
)
from opensquilla.engine.hooks.types import (
    CompactionHook,
    CompactionState,
    ToolHook,
    ToolHookCall,
    ToolHookResult,
    TurnEvent,
    TurnHook,
    TurnHookContext,
    TurnHookResult,
)

__all__ = [
    "CompactionHook",
    "CompactionState",
    "DefaultMemoryFlushHook",
    "DefaultTraceEmitterHook",
    "DefaultTranscriptHook",
    "NoopCompactionHook",
    "NoopToolHook",
    "NoopTurnHook",
    "ToolHook",
    "ToolHookCall",
    "ToolHookResult",
    "TurnEvent",
    "TurnHook",
    "TurnHookContext",
    "TurnHookResult",
    "build_default_turn_hooks",
]
