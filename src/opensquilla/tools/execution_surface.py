"""Engine-facing tool execution surface assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from opensquilla.provider.types import ToolDefinition
from opensquilla.tool_boundary import AgentToolHandler
from opensquilla.tools.dispatch import build_tool_handler
from opensquilla.tools.policy import apply_tool_policy_from_config
from opensquilla.tools.policy_runtime import (
    ToolSurfaceCapabilities,
    detect_runtime_tool_surface_capabilities,
    resolve_runtime_tool_surface,
)
from opensquilla.tools.registry import ToolRegistry, filter_by_profile, resolve_profile
from opensquilla.tools.types import CallerKind, ToolContext

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ToolExecutionSurface:
    """Provider-ready tool definitions and dispatch handler for a turn."""

    definitions: list[ToolDefinition]
    handler: AgentToolHandler | None
    profile: str
    context: ToolContext | None


def known_skill_names_for_dispatch(skill_loader: object | None) -> set[str]:
    """Return skill names that should produce skill/tool mismatch envelopes."""

    if skill_loader is None:
        return set()
    load_all = getattr(skill_loader, "load_all", None)
    if not callable(load_all):
        return set()
    try:
        return {
            skill.name
            for skill in load_all()
            if not getattr(skill, "disable_model_invocation", False)
        }
    except Exception:
        return set()


def apply_execution_runtime_capability_denies(
    ctx: ToolContext,
    *,
    session_manager: object | None = None,
    gateway_config: object | None = None,
) -> ToolContext:
    """Resolve runtime-dependent tool denials for an execution context."""

    detected = detect_runtime_tool_surface_capabilities(
        channel_backing=(
            ctx.caller_kind in {CallerKind.CHANNEL, CallerKind.WEB} and bool(ctx.channel_id)
        )
    )
    capabilities = ToolSurfaceCapabilities(
        session_manager=session_manager is not None,
        task_runtime=detected.task_runtime,
        scheduler=detected.scheduler,
        gateway_config=gateway_config is not None,
        channel_backing=detected.channel_backing,
        image_generation=detected.image_generation,
    )
    return resolve_runtime_tool_surface(ctx, capabilities=capabilities)


def resolve_tool_execution_context(
    registry: ToolRegistry,
    ctx: ToolContext | None,
    *,
    config: object | None = None,
    session_manager: object | None = None,
    gateway_config: object | None = None,
) -> ToolContext | None:
    """Apply declarative and runtime policy before definitions and dispatch."""

    if ctx is None:
        return None
    resolved = apply_tool_policy_from_config(
        ctx,
        available_tools=registry.list_names(),
        config=config,
    )
    return apply_execution_runtime_capability_denies(
        resolved,
        session_manager=session_manager,
        gateway_config=gateway_config,
    )


def build_tool_execution_surface(
    registry: ToolRegistry | None,
    ctx: ToolContext | None = None,
    *,
    config: object | None = None,
    session_manager: object | None = None,
    gateway_config: object | None = None,
    skill_loader: object | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolExecutionSurface:
    """Build provider-visible tool definitions and the matching dispatch handler."""

    if registry is None:
        return ToolExecutionSurface(
            definitions=[],
            handler=None,
            profile="owner_full",
            context=None,
        )

    active_ctx = resolve_tool_execution_context(
        registry,
        ctx,
        config=config,
        session_manager=session_manager,
        gateway_config=gateway_config,
    )
    profile = resolve_profile(active_ctx)
    if active_ctx is not None:
        log.debug(
            "tool_policy.policy_pre",
            allowed_tool_count=len(registry.to_tool_definitions(active_ctx)),
            denied_count=len(active_ctx.denied_tools),
            profile=profile.value,
        )
    log.info(
        "tool_context_created",
        caller_kind=active_ctx.caller_kind if active_ctx else "none",
        denied_count=len(active_ctx.denied_tools) if active_ctx else 0,
    )
    definitions = registry.to_tool_definitions(active_ctx)
    definitions = filter_by_profile(definitions, profile)
    log.debug(
        "tool_policy.profile_post",
        allowed_tool_count=len(definitions),
        denied_count=len(active_ctx.denied_tools) if active_ctx else 0,
        profile=profile.value,
    )
    if metadata is not None:
        metadata["tool_profile"] = profile.value

    return ToolExecutionSurface(
        definitions=definitions,
        handler=build_tool_handler(
            registry,
            active_ctx,
            known_skill_names=known_skill_names_for_dispatch(skill_loader),
        ),
        profile=profile.value,
        context=active_ctx,
    )


__all__ = [
    "ToolExecutionSurface",
    "apply_execution_runtime_capability_denies",
    "build_tool_execution_surface",
    "known_skill_names_for_dispatch",
    "resolve_tool_execution_context",
]
