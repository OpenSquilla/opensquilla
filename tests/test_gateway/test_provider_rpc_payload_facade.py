from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from opensquilla.gateway.provider_rpc_payloads import (
    build_provider_status_rpc_payload,
    list_provider_models_rpc_payload,
)
from opensquilla.provider import ModelInfo

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_PAYLOADS = ROOT / "src/opensquilla/gateway/provider_rpc_payloads.py"
RPC_PROVIDERS = ROOT / "src/opensquilla/gateway/rpc_providers.py"
RPC_MODELS = ROOT / "src/opensquilla/gateway/rpc_models.py"
PROVIDER_RUNTIME_STATUS = ROOT / "src/opensquilla/provider/runtime_status.py"
PROVIDER_MODEL_LISTING = ROOT / "src/opensquilla/provider/model_listing.py"


def _imports_from(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))
    return imports


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@dataclass(frozen=True)
class FakeStatusSpec:
    provider_id: str
    runtime_supported: bool = True
    env_key: str = "OPENROUTER_API_KEY"
    default_base_url: str = "https://openrouter.ai/api/v1"
    requires_api_key: bool = True
    requires_base_url: bool = False


class ListingStatusSelector:
    current_config = SimpleNamespace(provider="openrouter")

    async def list_models(self) -> list[dict[str, object]]:
        return [
            {"provider": "openrouter", "model_id": "openrouter/model"},
            {"provider": "ollama", "model_id": "ollama/model"},
        ]


class ListingModelSelector:
    async def list_models(self) -> list[object]:
        return [
            {
                "provider": "openrouter",
                "model_id": "a",
                "display_name": "A",
                "context_window": 123,
                "supports_tools": True,
                "input_cost_per_1k": 0.1,
                "output_cost_per_1k": 0.2,
            },
            ModelInfo(provider="ollama", model_id="b", supports_tools=True),
        ]


def _config(
    *,
    provider: str = "openrouter",
    model: str = "openrouter/model",
    api_key: str = "",
    base_url: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    )


@pytest.mark.asyncio
async def test_provider_status_rpc_payload_facade_preserves_wire_shape_and_filters() -> None:
    payload = await build_provider_status_rpc_payload(
        [
            FakeStatusSpec(provider_id="openrouter"),
            FakeStatusSpec(
                provider_id="ollama",
                env_key="",
                requires_api_key=False,
                default_base_url="",
            ),
        ],
        {"provider": "openrouter", "probeModels": True},
        provider_selector=ListingStatusSelector(),
        config=_config(api_key="secret-key", base_url="https://custom.example/v1"),
        environ={},
    )

    assert payload == {
        "activeProvider": "openrouter",
        "providers": [
            {
                "providerId": "openrouter",
                "active": True,
                "configured": True,
                "buildable": True,
                "model": "openrouter/model",
                "requiresApiKey": True,
                "apiKeyConfigured": True,
                "baseUrlConfigured": True,
                "error": None,
                "modelProbe": {
                    "attempted": True,
                    "status": "ok",
                    "count": 1,
                    "error": None,
                },
            }
        ],
        "count": 1,
    }
    assert "secret-key" not in repr(payload)


@pytest.mark.asyncio
async def test_model_list_rpc_payload_facade_preserves_wire_shape_and_filters() -> None:
    payload = await list_provider_models_rpc_payload(
        ListingModelSelector(),
        {"provider": "openrouter", "capabilities": ["tools"]},
    )

    assert payload == [
        {
            "id": "a",
            "name": "A",
            "provider": "openrouter",
            "contextWindow": 123,
            "capabilities": ["chat", "tools"],
            "pricing": {
                "inputPer1k": 0.1,
                "outputPer1k": 0.2,
            },
        }
    ]


def test_gateway_provider_rpc_handlers_import_payload_facade() -> None:
    provider_imports = _imports_from(RPC_PROVIDERS)
    model_imports = _imports_from(RPC_MODELS)

    assert (
        "opensquilla.gateway.provider_rpc_payloads",
        "build_provider_status_rpc_payload",
    ) in provider_imports
    assert (
        "opensquilla.provider.runtime_status",
        "build_provider_status_rpc_payload",
    ) not in provider_imports
    assert (
        "opensquilla.gateway.provider_rpc_payloads",
        "list_provider_models_rpc_payload",
    ) in model_imports
    assert (
        "opensquilla.provider.model_listing",
        "list_provider_models_rpc_payload",
    ) not in model_imports


def test_provider_modules_do_not_own_gateway_rpc_wire_helpers() -> None:
    facade_functions = _top_level_functions(GATEWAY_PAYLOADS)
    runtime_functions = _top_level_functions(PROVIDER_RUNTIME_STATUS)
    model_listing_functions = _top_level_functions(PROVIDER_MODEL_LISTING)

    assert "_provider_status_rpc_params" in facade_functions
    assert "_provider_status_report_to_wire" in facade_functions
    assert "_models_list_rpc_params" in facade_functions
    assert "_model_row_to_wire" in facade_functions

    assert "provider_model_probe_to_wire" not in runtime_functions
    assert "provider_status_row_to_wire" not in runtime_functions
    assert "provider_status_report_to_wire" not in runtime_functions
    assert "_provider_status_rpc_params" not in runtime_functions
    assert "_models_list_rpc_params" not in model_listing_functions
    assert "_model_row_to_wire" not in model_listing_functions
