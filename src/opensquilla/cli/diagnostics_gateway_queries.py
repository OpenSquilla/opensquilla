"""Gateway-backed diagnostics queries for CLI workflows."""

from __future__ import annotations

from typing import Any, cast

from opensquilla.cli.gateway_rpc import run_gateway_sync


def load_diagnostics_status(*, json_output: bool) -> dict[str, Any]:
    """Load effective diagnostics state from the running gateway."""

    async def _run(client: Any) -> dict[str, Any]:
        return cast(dict[str, Any], await client.call("diagnostics.status", {}))

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))


def set_diagnostics_enabled(
    *,
    enabled: bool,
    raw: bool | None = None,
    json_output: bool,
) -> dict[str, Any]:
    """Mutate runtime diagnostics state through the running gateway."""

    params: dict[str, object] = {"enabled": enabled}
    if raw is not None:
        params["raw"] = raw

    async def _run(client: Any) -> dict[str, Any]:
        return cast(dict[str, Any], await client.call("diagnostics.set", params))

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))
