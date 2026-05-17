"""Gateway-backed skill query helpers for CLI skill commands."""

from __future__ import annotations

from typing import Any, cast

from opensquilla.cli.gateway_rpc import run_gateway_sync


def load_gateway_skill(name: str, *, json_output: bool) -> dict[str, Any]:
    """Load one skill through the running gateway."""

    async def _run(client: Any) -> Any:
        return await client.call("skills.get", {"name": name})

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))


def update_gateway_skills(
    name: str | None,
    *,
    all_skills: bool,
    json_output: bool,
) -> dict[str, Any]:
    """Update one skill or all skills through the running gateway."""

    async def _run(client: Any) -> Any:
        params = {} if all_skills else {"name": name}
        return await client.call("skills.update", params)

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))
