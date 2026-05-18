from __future__ import annotations

import ast
from pathlib import Path

from opensquilla.gateway.config import GatewayConfig
from opensquilla.provider.runtime_config import (
    OPENROUTER_DEFAULT_PROVIDER_ROUTING,
    LlmRuntimeConfig,
    resolve_llm_runtime_config,
)

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "src/opensquilla/gateway"
PROVIDER = ROOT / "src/opensquilla/provider"
GATEWAY_LLM_RUNTIME = GATEWAY / "llm_runtime.py"
PROVIDER_RUNTIME_CONFIG = PROVIDER / "runtime_config.py"
PROVIDER_RUNTIME_ASSEMBLY = GATEWAY / "provider_runtime_assembly.py"
PROVIDER_RUNTIME_SYNC = GATEWAY / "provider_runtime_sync.py"


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


def _top_level_classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def _top_level_assignments(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_provider_layer_owns_runtime_llm_config_resolution() -> None:
    assert PROVIDER_RUNTIME_CONFIG.is_file()

    gateway_imports = _imports_from(GATEWAY_LLM_RUNTIME)
    provider_imports = _imports_from(PROVIDER_RUNTIME_CONFIG)
    assembly_imports = _imports_from(PROVIDER_RUNTIME_ASSEMBLY)
    sync_imports = _imports_from(PROVIDER_RUNTIME_SYNC)

    assert {
        ("opensquilla.provider.runtime_config", "LlmRuntimeConfig"),
        ("opensquilla.provider.runtime_config", "OPENROUTER_DEFAULT_PROVIDER_ROUTING"),
        ("opensquilla.provider.runtime_config", "provider_base_url_env_name"),
        ("opensquilla.provider.runtime_config", "resolve_llm_runtime_config"),
    } <= gateway_imports
    assert "LlmRuntimeConfig" not in _top_level_classes(GATEWAY_LLM_RUNTIME)
    assert "resolve_llm_runtime_config" not in _top_level_functions(GATEWAY_LLM_RUNTIME)
    assert "OPENROUTER_DEFAULT_PROVIDER_ROUTING" not in _top_level_assignments(
        GATEWAY_LLM_RUNTIME
    )

    assert "LlmRuntimeConfig" in _top_level_classes(PROVIDER_RUNTIME_CONFIG)
    assert "resolve_llm_runtime_config" in _top_level_functions(PROVIDER_RUNTIME_CONFIG)
    assert "OPENROUTER_DEFAULT_PROVIDER_ROUTING" in _top_level_assignments(
        PROVIDER_RUNTIME_CONFIG
    )
    assert ("opensquilla.provider.registry", "get_provider_spec") in provider_imports
    assert ("opensquilla.gateway.llm_runtime", "resolve_llm_runtime_config") not in (
        assembly_imports | sync_imports
    )
    assert (
        "opensquilla.provider.runtime_config",
        "resolve_llm_runtime_config",
    ) in assembly_imports
    assert (
        "opensquilla.provider.runtime_config",
        "resolve_llm_runtime_config",
    ) in sync_imports


def test_provider_runtime_config_preserves_env_and_routing_behavior(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example")
    cfg = GatewayConfig(llm={"provider": "deepseek", "api_key": "", "base_url": ""})

    runtime = resolve_llm_runtime_config(cfg)

    assert isinstance(runtime, LlmRuntimeConfig)
    assert runtime.provider == "deepseek"
    assert runtime.api_key == "deepseek-key"
    assert runtime.base_url == "https://deepseek.example"
    assert runtime.api_key_from_env is True
    assert runtime.base_url_from_env is True
    assert runtime.provider_routing == {}
    assert "deepseek/deepseek-v4-flash" in OPENROUTER_DEFAULT_PROVIDER_ROUTING

    openrouter_cfg = GatewayConfig(
        llm={
            "provider": "openrouter",
            "provider_routing": {"z-ai/glm-5.1": "z-ai/fp8"},
        }
    )
    openrouter_runtime = resolve_llm_runtime_config(openrouter_cfg)

    assert openrouter_runtime.provider_routing["deepseek/deepseek-v4-flash"] == "deepseek"
    assert openrouter_runtime.provider_routing["z-ai/glm-5.1"] == "z-ai/fp8"
