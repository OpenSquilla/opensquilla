"""Persistent raw tool-result storage for provider-context projections."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolResultRecord:
    handle: str
    tool_use_id: str
    tool_name: str
    sha256: str
    chars: int
    created_at: str
    content: str


class ToolResultStore:
    """Store full raw tool results that are omitted from provider context."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write(
        self,
        content: str,
        *,
        tool_use_id: str,
        tool_name: str,
    ) -> ToolResultRecord:
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        handle = f"tr-{secrets.token_hex(16)}"
        record = ToolResultRecord(
            handle=handle,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            sha256=sha,
            chars=len(content),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            content=content,
        )
        record_dir = self._record_dir(handle)
        record_dir.mkdir(parents=True, exist_ok=True)
        content_path = record_dir / "content.txt"
        meta_path = record_dir / "meta.json"
        if not content_path.exists():
            content_path.write_text(content, encoding="utf-8")
        meta = {
            "handle": record.handle,
            "tool_use_id": record.tool_use_id,
            "tool_name": record.tool_name,
            "sha256": record.sha256,
            "chars": record.chars,
            "created_at": record.created_at,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return record

    def read(self, handle: str) -> ToolResultRecord:
        normalized = _validate_handle(handle)
        record_dir = self._record_dir(normalized)
        meta_path = record_dir / "meta.json"
        content_path = record_dir / "content.txt"
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        content = content_path.read_text(encoding="utf-8")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if sha != meta.get("sha256"):
            raise ValueError("tool result hash mismatch")
        return ToolResultRecord(
            handle=normalized,
            tool_use_id=str(meta.get("tool_use_id") or ""),
            tool_name=str(meta.get("tool_name") or ""),
            sha256=sha,
            chars=len(content),
            created_at=str(meta.get("created_at") or ""),
            content=content,
        )

    def _record_dir(self, handle: str) -> Path:
        normalized = _validate_handle(handle)
        return self.root / normalized[3:5] / normalized


def _validate_handle(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("tr-"):
        raise ValueError("tool result handle is invalid")
    suffix = value[3:]
    if len(suffix) != 32 or any(ch not in "0123456789abcdef" for ch in suffix):
        raise ValueError("tool result handle is invalid")
    return value
