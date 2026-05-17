"""macOS Seatbelt backend with SBPL profile rendering.

This module deliberately renders profiles only and does not run commands yet.
It keeps the backend abstraction, policy translation, and availability probe
ready for future ``sandbox-exec`` execution support.

The Seatbelt profile language (SBPL) is a TinyScheme-derived DSL. The
baseline profile for opensquilla maps a :class:`SandboxPolicy` to three rules:

1. ``(deny default)`` — start from a deny-by-default posture.
2. ``(allow file-read* (subpath "<workspace>"))`` plus ``file-write*`` if
   the policy has ``workspace_rw``.
3. ``(deny network*)`` when ``policy.network == NetworkMode.NONE``.

:func:`_render_sbpl_skeleton` returns the profile string so the unit test
suite can assert shape without invoking ``sandbox-exec``. The runtime entry
point :meth:`SeatbeltBackend.run` raises :class:`NotImplementedError`; the
error message points at this file.
"""

from __future__ import annotations

from opensquilla.sandbox.backend.base import Backend
from opensquilla.sandbox.types import (
    NetworkMode,
    SandboxPolicy,
    SandboxRequest,
    SandboxResult,
)

_SANDBOX_EXEC = "sandbox-exec"


def _render_sbpl_skeleton(policy: SandboxPolicy) -> str:
    """Render the three-rule SBPL profile for ``policy``.

    The output is intentionally small and readable: each rule is on its own
    line so future execution support can extend it with additional allow rules
    (cache dirs, homebrew prefix, etc.) without reformatting.
    """
    lines: list[str] = [
        "(version 1)",
        "(deny default)",
    ]
    workspace = next(
        (m for m in policy.mounts if m.sandbox_path.as_posix() == "/workspace"),
        None,
    )
    if workspace is not None:
        lines.append(f'(allow file-read* (subpath "{workspace.host_path}"))')
        if policy.workspace_rw:
            lines.append(f'(allow file-write* (subpath "{workspace.host_path}"))')
    if policy.network == NetworkMode.NONE:
        lines.append("(deny network*)")
    else:
        lines.append("(allow network*)")
    return "\n".join(lines) + "\n"


class SeatbeltBackend(Backend):
    """macOS ``sandbox-exec`` backend with profile rendering only."""

    name = "seatbelt"

    def available(self) -> bool:
        # Backend.available() means "can execute SandboxRequest", not merely
        # "can render a profile". Keep this false until run() is implemented.
        return False

    async def run(self, request: SandboxRequest) -> SandboxResult:  # noqa: ARG002
        raise NotImplementedError(
            "macOS Seatbelt backend currently renders profiles only; "
            "process execution is pending — "
            "see opensquilla/sandbox/backend/seatbelt.py"
        )


__all__ = ["SeatbeltBackend", "_render_sbpl_skeleton"]
