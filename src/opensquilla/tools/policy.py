"""Tool policy resolution for runtime tool visibility and dispatch."""

from __future__ import annotations

from dataclasses import dataclass, replace

from opensquilla.tools import policy_config
from opensquilla.tools.types import InteractionMode, ToolContext

ToolPolicy = policy_config.ToolPolicy

_IMAGE_GENERATION_TOOL_NAMES: frozenset[str] = frozenset({"image_generate"})
_SESSION_READ_TOOL_NAMES: frozenset[str] = frozenset(
    {"session_status", "sessions_history", "sessions_list"}
)
_SESSION_RUNTIME_TOOL_NAMES: frozenset[str] = frozenset(
    {"sessions_send", "sessions_spawn", "sessions_yield"}
)
_CHANNEL_RUNTIME_TOOL_NAMES: frozenset[str] = frozenset({"message"})
_ADMIN_RUNTIME_TOOL_NAMES: frozenset[str] = frozenset({"agents_list", "subagents"})
_GATEWAY_RUNTIME_TOOL_NAMES: frozenset[str] = frozenset({"gateway"})
_SCHEDULER_RUNTIME_TOOL_NAMES: frozenset[str] = frozenset({"cron"})


@dataclass(frozen=True)
class ToolSurfaceCapabilities:
    """Runtime dependencies that determine whether registered tools can work."""

    session_manager: bool = False
    task_runtime: bool = False
    scheduler: bool = False
    gateway_config: bool = False
    channel_backing: bool = False
    image_generation: bool = True


def _detect_image_generation_capability() -> bool:
    try:
        from opensquilla.provider.image_generation_runtime import image_generation_available

        return image_generation_available()
    except Exception:
        return False


def tool_surface_capabilities_from_runtime(
    *,
    session_manager: object | None = None,
    task_runtime: object | None = None,
    scheduler: object | None = None,
    gateway_config: object | None = None,
    channel_manager: object | None = None,
    originating_envelope: object | None = None,
    image_generation: bool | None = None,
) -> ToolSurfaceCapabilities:
    """Build tool-surface capabilities from injected runtime dependencies."""

    return ToolSurfaceCapabilities(
        session_manager=session_manager is not None,
        task_runtime=task_runtime is not None,
        scheduler=scheduler is not None,
        gateway_config=gateway_config is not None,
        channel_backing=channel_manager is not None or originating_envelope is not None,
        image_generation=(
            _detect_image_generation_capability()
            if image_generation is None
            else image_generation
        ),
    )


def resolve_runtime_tool_surface(
    ctx: ToolContext,
    *,
    capabilities: ToolSurfaceCapabilities | None = None,
) -> ToolContext:
    """Resolve runtime-capability tool visibility into the context denylist."""

    caps = capabilities or ToolSurfaceCapabilities()
    denied_tools = set(ctx.denied_tools)
    allowed_tools = set(ctx.allowed_tools) if ctx.allowed_tools is not None else None

    if not caps.image_generation:
        denied_tools |= set(_IMAGE_GENERATION_TOOL_NAMES)
    if not caps.session_manager:
        denied_tools |= set(_SESSION_READ_TOOL_NAMES | _SESSION_RUNTIME_TOOL_NAMES)
    if not caps.task_runtime:
        denied_tools |= set(_SESSION_RUNTIME_TOOL_NAMES)
    if not caps.scheduler:
        denied_tools |= set(_SCHEDULER_RUNTIME_TOOL_NAMES)
    if not caps.gateway_config:
        denied_tools |= set(_GATEWAY_RUNTIME_TOOL_NAMES)

    if ctx.interaction_mode is InteractionMode.UNATTENDED:
        if not caps.channel_backing:
            denied_tools |= set(_CHANNEL_RUNTIME_TOOL_NAMES)
        denied_tools |= set(_ADMIN_RUNTIME_TOOL_NAMES)

    allowed_tools = policy_config.remove_denied_from_allowed(allowed_tools, denied_tools)
    return replace(ctx, allowed_tools=allowed_tools, denied_tools=denied_tools)


def detect_runtime_tool_surface_capabilities(
    *,
    channel_backing: bool = False,
) -> ToolSurfaceCapabilities:
    """Detect tool runtime dependencies from the currently wired built-ins."""

    session_manager = False
    task_runtime = False
    scheduler = False
    gateway_config = False
    image_generation = True
    try:
        from opensquilla.tools.builtin import sessions

        session_manager = sessions.session_manager_available()
        task_runtime = sessions.task_runtime_available()
    except Exception:
        pass
    try:
        from opensquilla.tools.builtin import admin

        scheduler = admin.scheduler_available()
        gateway_config = admin.gateway_config_available()
    except Exception:
        pass
    try:
        image_generation = _detect_image_generation_capability()
    except Exception:
        image_generation = False
    return ToolSurfaceCapabilities(
        session_manager=session_manager,
        task_runtime=task_runtime,
        scheduler=scheduler,
        gateway_config=gateway_config,
        channel_backing=channel_backing,
        image_generation=image_generation,
    )


def apply_tool_policy(
    ctx: ToolContext,
    *,
    available_tools: list[str],
    global_policy: ToolPolicy | None = None,
    agent_policy: ToolPolicy | None = None,
    default_channel_policy: ToolPolicy | None = None,
    channel_policy: ToolPolicy | None = None,
) -> ToolContext:
    """Return a ``ToolContext`` with resolved allow/deny sets.

    Global and agent policy establish the base allowlist and hard denies.
    Agent profile overrides global profile. Channel/default/sender layers can
    further restrict or add tools, but global/agent denies still win.
    """

    available = frozenset(available_tools)
    allowed_tools = set(ctx.allowed_tools) if ctx.allowed_tools is not None else None
    denied_tools = set(ctx.denied_tools)

    allowed_tools, denied_tools = policy_config.apply_base_policy(
        allowed_tools,
        denied_tools,
        global_policy,
        available,
    )
    allowed_tools, denied_tools = policy_config.apply_base_policy(
        allowed_tools,
        denied_tools,
        agent_policy,
        available,
        profile_overrides=True,
    )
    hard_denied = set(denied_tools)

    channel_denied: set[str] = set()
    allowed_tools, channel_denied = policy_config.apply_channel_layer(
        allowed_tools,
        channel_denied,
        default_channel_policy,
        available,
    )
    allowed_tools, channel_denied = policy_config.apply_sender_layer(
        allowed_tools,
        channel_denied,
        policy_config.sender_policy(default_channel_policy, ctx.sender_id),
        available,
    )
    allowed_tools, channel_denied = policy_config.apply_channel_layer(
        allowed_tools,
        channel_denied,
        channel_policy,
        available,
    )
    allowed_tools, channel_denied = policy_config.apply_sender_layer(
        allowed_tools,
        channel_denied,
        policy_config.sender_policy(channel_policy, ctx.sender_id),
        available,
    )

    denied_tools = hard_denied | channel_denied
    if allowed_tools is not None:
        allowed_tools -= denied_tools

    return replace(ctx, allowed_tools=allowed_tools, denied_tools=denied_tools)


def apply_tool_policy_layer(
    ctx: ToolContext,
    policy: object,
    *,
    available_tools: list[str] | set[str] | frozenset[str],
    hard_denied: set[str] | frozenset[str] | None = None,
) -> ToolContext:
    """Apply one declarative policy layer to an existing context.

    This is used for persisted cron job policy carried through route metadata.
    It intentionally keeps the caller's current allowlist unless the policy
    selects a narrower named profile, and reapplies ``hard_denied`` at the end
    so lower layers cannot revive denied tools.
    """

    parsed = policy_config.policy_from_config(policy)
    if parsed is None:
        return ctx
    allowed_tools = set(ctx.allowed_tools) if ctx.allowed_tools is not None else None
    denied_tools = set(ctx.denied_tools)
    allowed_tools, denied_tools = policy_config.apply_base_policy(
        allowed_tools,
        denied_tools,
        parsed,
        frozenset(available_tools),
        profile_overrides=False,
    )
    if hard_denied:
        denied_tools |= set(hard_denied)
    if allowed_tools is not None:
        allowed_tools -= denied_tools
    return replace(ctx, allowed_tools=allowed_tools, denied_tools=denied_tools)


def apply_tool_policy_from_config(
    ctx: ToolContext,
    *,
    available_tools: list[str],
    config: object | None,
) -> ToolContext:
    """Apply config-shaped tool policy to a context.

    Supported config shape intentionally mirrors the documented policy concepts:
    ``config.tools``, ``config.agents[agent_id].tools`` or
    ``config.agents.list[].tools``, and channel entries such as
    ``config.channels.telegram.groups["room"].tools`` with optional
    ``toolsBySender``.
    """

    if config is None:
        return ctx
    default_channel_policy, channel_policy = policy_config.channel_entry_policy_from_config(
        config, ctx
    )
    return apply_tool_policy(
        ctx,
        available_tools=available_tools,
        global_policy=policy_config.policy_from_config(policy_config.get_field(config, "tools")),
        agent_policy=policy_config.agent_policy_from_config(config, ctx.agent_id),
        default_channel_policy=default_channel_policy,
        channel_policy=channel_policy,
    )
