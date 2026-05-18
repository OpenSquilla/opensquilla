from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "src/opensquilla/gateway"
RPC_PACKAGE = GATEWAY / "rpc/__init__.py"
RPC_ONBOARDING = GATEWAY / "rpc_onboarding.py"
RPC_ONBOARDING_PROVIDERS = GATEWAY / "rpc_onboarding_providers.py"


def _imports_from(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        (node.module or "", alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def _registered_methods(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "method"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                methods.add(decorator.args[0].value)
    return methods


def test_provider_onboarding_runtime_methods_live_in_provider_boundary() -> None:
    assert RPC_ONBOARDING_PROVIDERS.exists()

    provider_methods = {
        "onboarding.provider.configure",
        "onboarding.imageGeneration.configure",
    }

    assert provider_methods.isdisjoint(_registered_methods(RPC_ONBOARDING))
    assert provider_methods <= _registered_methods(RPC_ONBOARDING_PROVIDERS)

    provider_imports = _imports_from(RPC_ONBOARDING_PROVIDERS)
    onboarding_imports = _imports_from(RPC_ONBOARDING)

    assert (
        "opensquilla.onboarding.mutations",
        "upsert_llm_provider",
    ) in provider_imports
    assert (
        "opensquilla.onboarding.mutations",
        "upsert_image_generation_provider",
    ) in provider_imports
    assert (
        "opensquilla.gateway.provider_runtime_sync",
        "sync_provider_selector",
    ) in provider_imports
    assert (
        "opensquilla.gateway.provider_runtime_sync",
        "sync_image_generation",
    ) in provider_imports

    assert (
        "opensquilla.provider.image_generation_runtime",
        "configure_image_generation",
    ) not in onboarding_imports
    assert (
        "opensquilla.provider.image_generation_runtime",
        "configure_image_generation",
    ) not in provider_imports


def test_rpc_package_imports_provider_onboarding_boundary_after_core_onboarding() -> None:
    tree = ast.parse(RPC_PACKAGE.read_text(encoding="utf-8"), filename=str(RPC_PACKAGE))
    imported_modules = [
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    ]

    assert "opensquilla.gateway.rpc_onboarding" in imported_modules
    assert "opensquilla.gateway.rpc_onboarding_providers" in imported_modules
    assert imported_modules.index("opensquilla.gateway.rpc_onboarding") < (
        imported_modules.index("opensquilla.gateway.rpc_onboarding_providers")
    )
