"""Shared tool-result budget helpers.

The budget applies at tool boundaries, not at skill boundaries, so installed
skills cannot bypass it by asking for more fetches or larger outputs.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolResultBudgetClass(StrEnum):
    EXTERNAL = "external"
    LOCAL = "local"
    ARTIFACT = "artifact"
    ERROR = "error"
    CONTROL = "control"
    UNKNOWN = "unknown"


EXTERNAL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "http_request",
        "web_fetch",
        "web_search",
    }
)

CONTROL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "sessions_yield",
    }
)


@dataclass(frozen=True)
class ToolResultBudgetPolicy:
    max_single_tool_result_chars: int = 16_000
    max_single_external_result_chars: int = 12_000
    max_tool_result_chars_per_turn: int = 96_000
    max_external_tool_result_chars_per_turn: int = 48_000
    max_web_fetch_chars: int = 12_000
    max_web_search_results: int = 10


DEFAULT_TOOL_RESULT_BUDGET_POLICY = ToolResultBudgetPolicy()


@dataclass(frozen=True)
class ToolResultBudgetDecision:
    content: str
    changed: bool
    original_chars: int
    returned_chars: int
    budget_class: ToolResultBudgetClass


class ToolResultBudgetTracker:
    """Concurrency-safe per-turn accounting for normalized result previews."""

    def __init__(self, policy: ToolResultBudgetPolicy | None = None) -> None:
        self.policy = policy or DEFAULT_TOOL_RESULT_BUDGET_POLICY
        self._lock = asyncio.Lock()
        self._tool_chars_used = 0
        self._external_chars_used = 0

    async def normalize(
        self,
        *,
        tool_name: str,
        content: str,
        budget_class: ToolResultBudgetClass,
        is_error: bool = False,
    ) -> ToolResultBudgetDecision:
        if not isinstance(content, str):
            content = str(content)
        if is_error and budget_class is not ToolResultBudgetClass.CONTROL:
            budget_class = ToolResultBudgetClass.ERROR
        if budget_class is ToolResultBudgetClass.ARTIFACT:
            return ToolResultBudgetDecision(
                content=content,
                changed=False,
                original_chars=len(content),
                returned_chars=len(content),
                budget_class=budget_class,
            )
        if budget_class is ToolResultBudgetClass.CONTROL:
            single_limit = self.policy.max_single_tool_result_chars
        elif budget_class is ToolResultBudgetClass.EXTERNAL:
            single_limit = self.policy.max_single_external_result_chars
        else:
            single_limit = self.policy.max_single_tool_result_chars

        original_chars = len(content)
        async with self._lock:
            remaining_total = max(
                0,
                self.policy.max_tool_result_chars_per_turn - self._tool_chars_used,
            )
            remaining_external = (
                max(
                    0,
                    self.policy.max_external_tool_result_chars_per_turn
                    - self._external_chars_used,
                )
                if budget_class is ToolResultBudgetClass.EXTERNAL
                else remaining_total
            )
            allowed = max(0, min(single_limit, remaining_total, remaining_external))
            if original_chars <= allowed:
                self._tool_chars_used += original_chars
                if budget_class is ToolResultBudgetClass.EXTERNAL:
                    self._external_chars_used += original_chars
                return ToolResultBudgetDecision(
                    content=content,
                    changed=False,
                    original_chars=original_chars,
                    returned_chars=original_chars,
                    budget_class=budget_class,
                )

            compacted = compact_tool_result_content(
                tool_name=tool_name,
                content=content,
                max_preview_chars=allowed,
                budget_class=budget_class,
                is_error=is_error,
            )
            returned_chars = _preview_chars(compacted)
            self._tool_chars_used += returned_chars
            if budget_class is ToolResultBudgetClass.EXTERNAL:
                self._external_chars_used += returned_chars
            return ToolResultBudgetDecision(
                content=compacted,
                changed=True,
                original_chars=original_chars,
                returned_chars=returned_chars,
                budget_class=budget_class,
            )


def resolve_budget_class(tool_name: str, explicit: Any = None) -> ToolResultBudgetClass:
    if isinstance(explicit, ToolResultBudgetClass):
        return explicit
    if isinstance(explicit, str):
        try:
            return ToolResultBudgetClass(explicit)
        except ValueError:
            pass
    if tool_name in CONTROL_TOOL_NAMES:
        return ToolResultBudgetClass.CONTROL
    if tool_name in EXTERNAL_TOOL_NAMES:
        return ToolResultBudgetClass.EXTERNAL
    return ToolResultBudgetClass.UNKNOWN


def clamp_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    policy: ToolResultBudgetPolicy,
) -> dict[str, Any]:
    next_args = dict(arguments)
    if tool_name == "web_fetch":
        requested = next_args.get("max_chars")
        if isinstance(requested, int):
            next_args["max_chars"] = min(max(100, requested), policy.max_web_fetch_chars)
        elif requested is None:
            next_args["max_chars"] = policy.max_web_fetch_chars
    elif tool_name == "web_search":
        requested = next_args.get("max_results")
        if isinstance(requested, int):
            next_args["max_results"] = min(max(1, requested), policy.max_web_search_results)
        elif requested is None:
            next_args["max_results"] = policy.max_web_search_results
    return next_args


def compact_tool_result_content(
    *,
    tool_name: str,
    content: str,
    max_preview_chars: int,
    budget_class: ToolResultBudgetClass,
    is_error: bool = False,
) -> str:
    max_preview_chars = max(0, max_preview_chars)
    original_chars = len(content)
    if budget_class is ToolResultBudgetClass.CONTROL:
        return _compact_control_json(
            tool_name=tool_name,
            content=content,
            max_preview_chars=max_preview_chars,
            original_chars=original_chars,
            budget_class=budget_class,
        )
    preview = content[:max_preview_chars]
    payload: dict[str, Any] = {
        "tool_result_budget_applied": True,
        "result_truncated": True,
        "result_original_chars": original_chars,
        "result_returned_chars": len(preview),
        "budget_class": budget_class.value,
        "tool": tool_name,
        "is_error": bool(is_error),
        "preview": preview,
    }
    return json.dumps(payload, ensure_ascii=False)


def _compact_control_json(
    *,
    tool_name: str,
    content: str,
    max_preview_chars: int,
    original_chars: int,
    budget_class: ToolResultBudgetClass,
) -> str:
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        preview = content[:max_preview_chars]
        return json.dumps(
            {
                "tool_result_budget_applied": True,
                "result_truncated": True,
                "result_original_chars": original_chars,
                "result_returned_chars": len(preview),
                "budget_class": budget_class.value,
                "tool": tool_name,
                "preview": preview,
            },
            ensure_ascii=False,
        )
    if not isinstance(payload, dict):
        preview = content[:max_preview_chars]
        return json.dumps(
            {
                "tool_result_budget_applied": True,
                "result_truncated": True,
                "result_original_chars": original_chars,
                "result_returned_chars": len(preview),
                "budget_class": budget_class.value,
                "tool": tool_name,
                "preview": preview,
            },
            ensure_ascii=False,
        )

    compacted = dict(payload)
    for key, value in list(compacted.items()):
        if isinstance(value, str) and len(value) > max_preview_chars:
            compacted[key] = value[:max_preview_chars]
    compacted["tool_result_budget_applied"] = True
    compacted["result_truncated"] = True
    compacted["result_original_chars"] = original_chars
    compacted["result_returned_chars"] = _string_value_chars(compacted)
    compacted["budget_class"] = budget_class.value
    compacted["tool"] = tool_name
    return json.dumps(compacted, ensure_ascii=False)


def _preview_chars(rendered: str) -> int:
    try:
        payload = json.loads(rendered)
    except (TypeError, ValueError):
        return len(rendered)
    if isinstance(payload, dict):
        value = payload.get("result_returned_chars")
        if isinstance(value, int):
            return value
    return len(rendered)


def _string_value_chars(payload: dict[str, Any]) -> int:
    total = 0
    for value in payload.values():
        if isinstance(value, str):
            total += len(value)
    return total
