"""OpenSquilla adapter for the copied V4 Phase 3 model router bundle."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import structlog
import yaml

from opensquilla.squilla_router._v4_phase3_adapter import (
    find_valid_tier,
    normalize_adapter_result,
    normalize_unavailable_adapter_result,
    select_prompt_hint,
)

log = structlog.get_logger(__name__)


def default_bundle_dir() -> Path:
    """Return the repository-bundled V4 Phase 3 runtime asset directory."""
    return Path(__file__).resolve().parent / "models" / "v4.2_phase3_inference"


@contextmanager
def runtime_src_import_path(bundle_dir: Path) -> Iterator[None]:
    """Temporarily expose the copied bundle's ``runtime_src`` import root."""
    old_path = list(sys.path)
    sys.path.insert(0, str(bundle_dir / "runtime_src"))
    try:
        yield
    finally:
        sys.path[:] = old_path


def _find_valid_tier(start_tier: str, valid_tiers: list[str]) -> str:
    return find_valid_tier(start_tier, valid_tiers)


class V4Phase3Strategy:
    """History-aware strategy wrapping the delivered V4 Phase 3 inference core."""

    requires_history = True
    source = "v4_phase3"

    def __init__(
        self,
        bundle_dir: str | Path | None = None,
        confidence_threshold: float = 0.5,
        require_router_runtime: bool = False,
        use_aux_head: bool | None = None,
    ) -> None:
        self.bundle_dir = Path(bundle_dir) if bundle_dir else default_bundle_dir()
        self._threshold = confidence_threshold
        self._require_router_runtime = require_router_runtime
        self._core: Any | None = None
        self._request_type: Any | None = None
        self._config: dict[str, Any] = {}
        self._model_version = "unknown"
        self._available = False

        try:
            self._init_runtime(use_aux_head=use_aux_head)
        except Exception as exc:
            log.warning(
                "v4_phase3.init_failed",
                bundle_dir=str(self.bundle_dir),
                error=str(exc),
            )
            if require_router_runtime:
                raise RuntimeError(f"failed to initialize V4 Phase 3 router: {exc}") from exc

    def _init_runtime(self, use_aux_head: bool | None) -> None:
        self._validate_bundle()
        self._config = (
            yaml.safe_load((self.bundle_dir / "router.runtime.yaml").read_text(encoding="utf-8"))
            or {}
        )
        self._model_version = self._read_model_version()

        with runtime_src_import_path(self.bundle_dir):
            from src.router.inference.core import InferenceCore
            from src.router.inference.types import InferenceRequest

            resolved_aux_head = (
                bool(self._config.get("v4", {}).get("aux_head_inference", False))
                if use_aux_head is None
                else use_aux_head
            )
            self._request_type = InferenceRequest
            self._core = InferenceCore.from_model_dir(
                self.bundle_dir,
                self._config,
                use_aux_head=resolved_aux_head,
            )
        self._available = True

    def _validate_bundle(self) -> None:
        required = ("runtime_src", "router.runtime.yaml")
        missing = [name for name in required if not (self.bundle_dir / name).exists()]
        if missing:
            raise FileNotFoundError(f"missing V4 bundle files: {missing}")

    def _read_model_version(self) -> str:
        for name in ("version.json", "inference_manifest.json"):
            path = self.bundle_dir / name
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in ("version", "model_version", "bundle_version"):
                value = data.get(key)
                if value:
                    return str(value)
        return "unknown"

    async def classify(
        self,
        message: str,
        valid_tiers: list[str],
        routing_history: list[dict] | None = None,
        prev_assistant_text: str | None = None,
        prev_assistant_usage: dict | None = None,
        history_user_texts: list[str] | None = None,
        flags_text_override: str | None = None,
    ) -> tuple[str, float, str, dict]:
        """Classify a turn into OpenSquilla tier format."""
        if not self._available or self._core is None or self._request_type is None:
            return self._unavailable_classify(valid_tiers)

        try:
            request = self._build_request(
                message,
                routing_history or [],
                prev_assistant_text=prev_assistant_text,
                prev_assistant_usage=prev_assistant_usage,
                history_user_texts=history_user_texts,
                flags_text_override=flags_text_override,
            )
            result = self._core.predict(request)
            return self._map_result(result, valid_tiers, message)
        except Exception as exc:
            log.warning("v4_phase3.predict_failed", error=str(exc), exc_info=True)
            if self._require_router_runtime:
                raise
            return self._unavailable_classify(valid_tiers)

    def _unavailable_classify(
        self,
        valid_tiers: list[str],
    ) -> tuple[str, float, str, dict]:
        return normalize_unavailable_adapter_result(
            valid_tiers=valid_tiers,
            model_version=self._model_version,
            source="v4_unavailable",
        )

    def _build_request(
        self,
        message: str,
        routing_history: list[dict],
        *,
        prev_assistant_text: str | None = None,
        prev_assistant_usage: dict | None = None,
        history_user_texts: list[str] | None = None,
        flags_text_override: str | None = None,
    ) -> Any:
        if history_user_texts is None:
            history_texts = [str(entry["text"]) for entry in routing_history if entry.get("text")]
        else:
            history_texts = [str(text) for text in history_user_texts if text]
        context_tokens_est = max(
            0,
            (
                len(message)
                + sum(len(text) for text in history_texts)
                + len(prev_assistant_text or "")
            )
            // 4,
        )
        decisions: list[Any] = []
        for entry in routing_history:
            route_class = entry.get("final_route_class") or entry.get("route_class")
            if route_class:
                decisions.append(
                    SimpleNamespace(
                        route_class=str(route_class),
                        difficulty=float(
                            entry.get("difficulty_score", entry.get("difficulty", 0.0)) or 0.0
                        ),
                        margin=float(entry.get("margin", 0.0) or 0.0),
                    )
                )

        request_type = self._request_type
        if request_type is None:
            raise RuntimeError("V4 Phase 3 router request type is not initialized")

        return request_type(
            current_user_text=message,
            history_user_texts=history_texts,
            prev_assistant_text=prev_assistant_text,
            prev_assistant_usage=prev_assistant_usage,
            prev_route_decisions=decisions,
            flags_text_override=flags_text_override,
            context_metadata={
                "turn_index": len(routing_history),
                "history_user_turn_count": len(history_texts),
                "context_tokens_est": context_tokens_est,
                "has_code_block": "```" in message,
                "has_prev_assistant": bool(prev_assistant_text),
            },
        )

    def _map_result(
        self,
        result: Any,
        valid_tiers: list[str],
        message: str,
    ) -> tuple[str, float, str, dict]:
        return normalize_adapter_result(
            result,
            valid_tiers=valid_tiers,
            message=message,
            model_version=self._model_version,
            runtime_config=self._config,
            source=self.source,
        )

    def _prompt_hint(self, prompt_policy: str, message: str | None = None) -> str | None:
        return select_prompt_hint(self._config, prompt_policy, message)
