"""Explicit generated-artifact publication tool."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from opensquilla.artifacts import (
    DEFAULT_ARTIFACT_DISK_BUDGET_BYTES,
    DEFAULT_ARTIFACT_MAX_BYTES,
    ArtifactBudgetError,
    ArtifactStore,
    artifact_payload,
)
from opensquilla.tools.registry import tool
from opensquilla.tools.types import ToolError, current_tool_context


@tool(
    name="publish_artifact",
    description=(
        "Publish an existing workspace file as a generated artifact for the user to download. "
        "Only files inside the active workspace are allowed. "
        "The user's UI shows a clickable download chip automatically; do not include any URL "
        "in your reply — just confirm the file is ready."
    ),
    params={
        "path": {
            "type": "string",
            "description": "Workspace-relative or in-workspace absolute path to publish.",
        },
        "name": {
            "type": "string",
            "description": "Optional download filename. Defaults to the source filename.",
        },
        "mime": {
            "type": "string",
            "description": "Optional MIME type. Defaults to a filename guess.",
        },
    },
    required=["path"],
)
async def publish_artifact(
    path: str,
    name: str | None = None,
    mime: str | None = None,
) -> str:
    ctx = current_tool_context.get()
    if ctx is None:
        raise ToolError("publish_artifact requires tool context")
    if not ctx.workspace_dir:
        raise ToolError("publish_artifact requires an active workspace")
    if not ctx.artifact_media_root:
        raise ToolError("artifact storage is not configured for this turn")
    if not ctx.artifact_session_id or not ctx.session_key:
        raise ToolError("artifact session scope is not configured for this turn")

    workspace = Path(ctx.workspace_dir).resolve()
    raw_path = Path(path)
    target = (raw_path if raw_path.is_absolute() else workspace / raw_path).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ToolError(f"artifact path is outside workspace: {path}") from exc
    if not target.exists():
        raise ToolError(f"artifact file not found: {path}")
    if not target.is_file():
        raise ToolError(f"artifact path is not a file: {path}")

    artifact_mime = (mime or mimetypes.guess_type(name or target.name)[0] or "").strip()
    if not artifact_mime:
        artifact_mime = "application/octet-stream"

    store = ArtifactStore(ctx.artifact_media_root)
    try:
        ref = store.publish_file(
            target,
            session_id=ctx.artifact_session_id,
            session_key=ctx.session_key,
            name=name or target.name,
            mime=artifact_mime,
            source="publish_artifact",
            max_bytes=ctx.artifact_max_bytes
            if ctx.artifact_max_bytes is not None
            else DEFAULT_ARTIFACT_MAX_BYTES,
            disk_budget_bytes=ctx.artifact_disk_budget_bytes
            if ctx.artifact_disk_budget_bytes is not None
            else DEFAULT_ARTIFACT_DISK_BUDGET_BYTES,
        )
    except ArtifactBudgetError as exc:
        raise ToolError(str(exc)) from exc
    except FileNotFoundError as exc:
        if not target.exists():
            raise ToolError(f"artifact file not found: {path}") from exc
        raise ToolError(f"artifact storage path is unavailable: {exc}") from exc

    payload = artifact_payload(ref)
    ctx.published_artifacts.append(payload)
    llm_artifact = {k: v for k, v in payload.items() if k != "download_url"}
    return json.dumps(
        {
            "status": "published",
            "artifact": llm_artifact,
            "note": (
                "The user already sees a clickable download button rendered by the UI. "
                "Do not include any URL in your reply."
            ),
        },
        ensure_ascii=False,
    )
