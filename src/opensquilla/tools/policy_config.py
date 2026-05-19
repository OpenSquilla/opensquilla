"""Declarative tool policy config and selector helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

from opensquilla.tools.types import ToolContext

_TOOL_GROUPS: Mapping[str, frozenset[str]] = {
    "group:runtime": frozenset({"exec_command", "background_process"}),
    "group:fs": frozenset(
        {
            "read_file",
            "write_file",
            "edit_file",
            "apply_patch",
            "list_dir",
            "glob_search",
            "grep_search",
        }
    ),
    "group:sessions": frozenset(
        {"sessions_list", "sessions_history", "sessions_send", "sessions_spawn", "session_status"}
    ),
    "group:memory": frozenset({"memory_search", "memory_get"}),
    "group:web": frozenset({"web_search", "web_fetch", "http_request"}),
    "group:messaging": frozenset({"message"}),
    # Trusted host/gateway tools intentionally do not imply OS sandbox
    # execution. They remain addressable for explicit allow/deny policy so the
    # sandboxed-agent tool surface is not confused with operator-owned host
    # mutation paths.
    "group:trusted_host": frozenset(
        {
            "install_skill_deps",
            "skill_create",
            "skill_edit",
            "skill_delete",
        }
    ),
}

_TOOL_PROFILES: Mapping[str, frozenset[str] | None] = {
    "full": None,
    "minimal": frozenset({"session_status"}),
    "memory_only": _TOOL_GROUPS["group:memory"],
    "coding": (
        _TOOL_GROUPS["group:fs"]
        | _TOOL_GROUPS["group:runtime"]
        | _TOOL_GROUPS["group:sessions"]
        | _TOOL_GROUPS["group:memory"]
    ),
    "messaging": _TOOL_GROUPS["group:messaging"]
    | frozenset({"sessions_list", "sessions_history", "sessions_send", "session_status"}),
}


@dataclass(frozen=True)
class ToolPolicy:
    """Declarative tool policy layer."""

    profile: str | None = None
    allow: frozenset[str] = frozenset()
    deny: frozenset[str] = frozenset()
    also_allow: frozenset[str] = frozenset()
    by_sender: Mapping[str, ToolPolicy] = field(default_factory=dict)


def expand_selectors(selectors: frozenset[str], available_tools: frozenset[str]) -> set[str]:
    expanded: set[str] = set()
    for selector in selectors:
        item = selector.strip()
        if not item:
            continue
        if item == "*":
            expanded.update(available_tools)
            continue
        if item in _TOOL_GROUPS:
            expanded.update(_TOOL_GROUPS[item] & available_tools)
            continue
        if any(ch in item for ch in "*?[]"):
            expanded.update(tool for tool in available_tools if fnmatchcase(tool, item))
            continue
        if item in available_tools:
            expanded.add(item)
    return expanded


def profile_allowlist(profile: str | None, available_tools: frozenset[str]) -> set[str] | None:
    if not profile:
        return None
    key = profile.strip().lower()
    if key not in _TOOL_PROFILES:
        raise ValueError(f"unknown tool profile: {profile}")
    expanded = _TOOL_PROFILES[key]
    if expanded is None:
        return None
    return set(expanded & available_tools)


def add_allowed(
    allowed_tools: set[str] | None,
    additions: set[str],
) -> set[str] | None:
    if allowed_tools is None:
        return None
    return allowed_tools | additions


def apply_base_policy(
    allowed_tools: set[str] | None,
    denied_tools: set[str],
    policy: ToolPolicy | None,
    available_tools: frozenset[str],
    *,
    profile_overrides: bool = False,
) -> tuple[set[str] | None, set[str]]:
    if policy is None:
        return allowed_tools, denied_tools

    profile_allowed = profile_allowlist(policy.profile, available_tools)
    if profile_allowed is not None or (profile_overrides and policy.profile == "full"):
        allowed_tools = profile_allowed

    allowed_tools = add_allowed(
        allowed_tools,
        expand_selectors(policy.allow | policy.also_allow, available_tools),
    )
    denied_tools = denied_tools | expand_selectors(policy.deny, available_tools)
    if allowed_tools is not None:
        allowed_tools -= denied_tools
    return allowed_tools, denied_tools


def matches_sender(selector: str, sender_id: str | None) -> bool:
    if selector == "*":
        return True
    if not sender_id:
        return False
    return selector == f"id:{sender_id}" or selector == sender_id


def get_field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def string_set(value: object) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(item) for item in value if str(item).strip())
    return frozenset()


def policy_from_config(value: object) -> ToolPolicy | None:
    if value is None:
        return None
    if isinstance(value, ToolPolicy):
        return value

    tools_value = get_field(value, "tools")
    sender_value = get_field(value, "toolsBySender", get_field(value, "tools_by_sender"))
    if tools_value is not None or sender_value is not None:
        base = policy_from_config(tools_value) or ToolPolicy()
        return ToolPolicy(
            profile=base.profile,
            allow=base.allow,
            deny=base.deny,
            also_allow=base.also_allow,
            by_sender=sender_policies_from_config(sender_value),
        )

    profile = get_field(value, "profile")
    return ToolPolicy(
        profile=str(profile) if profile is not None else None,
        allow=string_set(get_field(value, "allow")),
        deny=string_set(get_field(value, "deny")),
        also_allow=string_set(get_field(value, "alsoAllow", get_field(value, "also_allow"))),
        by_sender=sender_policies_from_config(
            get_field(value, "by_sender", get_field(value, "bySender"))
        ),
    )


def sender_policies_from_config(value: object) -> Mapping[str, ToolPolicy]:
    if not isinstance(value, Mapping):
        return {}
    policies: dict[str, ToolPolicy] = {}
    for selector, policy_value in value.items():
        policy = policy_from_config(policy_value)
        if policy is not None:
            policies[str(selector)] = policy
    return policies


def sender_policy(policy: ToolPolicy | None, sender_id: str | None) -> ToolPolicy | None:
    if policy is None:
        return None
    for selector, candidate in policy.by_sender.items():
        if matches_sender(selector, sender_id):
            return candidate
    return None


def remove_denied_from_allowed(
    allowed_tools: set[str] | None,
    denied_tools: set[str],
) -> set[str] | None:
    if allowed_tools is not None:
        allowed_tools -= denied_tools
    return allowed_tools


def agent_policy_from_config(config: object, agent_id: str) -> ToolPolicy | None:
    agents = get_field(config, "agents")
    if isinstance(agents, Mapping):
        return policy_from_config(get_field(agents.get(agent_id), "tools"))

    entries = agents if isinstance(agents, list | tuple) else get_field(agents, "list", [])
    if isinstance(entries, list | tuple):
        for entry in entries:
            if get_field(entry, "id") == agent_id:
                return policy_from_config(get_field(entry, "tools"))
    return None


def channel_entry_policy_from_config(
    config: object, ctx: ToolContext
) -> tuple[
    ToolPolicy | None,
    ToolPolicy | None,
]:
    if not ctx.channel_kind:
        return None, None

    channels = get_field(config, "channels")
    channel_cfg = get_field(channels, ctx.channel_kind)
    if channel_cfg is None:
        return None, None

    entries: object = None
    for field_name in ("groups", "channels", "rooms"):
        entries = get_field(channel_cfg, field_name)
        if isinstance(entries, Mapping):
            break
    if not isinstance(entries, Mapping):
        return None, None

    default_policy = policy_from_config(entries.get("*"))
    specific_policy = policy_from_config(entries.get(ctx.channel_id or ""))
    return default_policy, specific_policy


def apply_channel_layer(
    allowed_tools: set[str] | None,
    channel_denied: set[str],
    policy: ToolPolicy | None,
    available_tools: frozenset[str],
) -> tuple[set[str] | None, set[str]]:
    if policy is None:
        return allowed_tools, channel_denied
    allowed_tools = add_allowed(
        allowed_tools,
        expand_selectors(policy.allow | policy.also_allow, available_tools),
    )
    channel_denied |= expand_selectors(policy.deny, available_tools)
    return allowed_tools, channel_denied


def apply_sender_layer(
    allowed_tools: set[str] | None,
    channel_denied: set[str],
    policy: ToolPolicy | None,
    available_tools: frozenset[str],
) -> tuple[set[str] | None, set[str]]:
    if policy is None:
        return allowed_tools, channel_denied
    also_allowed = expand_selectors(policy.also_allow, available_tools)
    channel_denied -= also_allowed
    allowed_tools = add_allowed(allowed_tools, expand_selectors(policy.allow, available_tools))
    allowed_tools = add_allowed(allowed_tools, also_allowed)
    channel_denied |= expand_selectors(policy.deny, available_tools)
    return allowed_tools, channel_denied
