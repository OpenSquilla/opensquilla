"""Provider runtime status helpers for adapter surfaces."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .selector import ProviderBuildError, build_provider


class ProviderStatusSpec(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def runtime_supported(self) -> bool: ...

    @property
    def env_key(self) -> str: ...

    @property
    def default_base_url(self) -> str: ...

    @property
    def requires_api_key(self) -> bool: ...

    @property
    def requires_base_url(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProviderModelProbe:
    attempted: bool
    status: str
    count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class ProviderStatusRow:
    provider_id: str
    active: bool
    configured: bool
    buildable: bool
    model: str
    requires_api_key: bool
    api_key_configured: bool
    base_url_configured: bool
    error: str | None
    model_probe: ProviderModelProbe


@dataclass(frozen=True, slots=True)
class ProviderStatusReport:
    active_provider: str | None
    rows: tuple[ProviderStatusRow, ...]


async def build_provider_status_report(
    specs: Iterable[ProviderStatusSpec],
    *,
    provider_selector: Any | None,
    config: Any | None,
    provider_filter: str | None = None,
    probe_models: bool = False,
    environ: Mapping[str, str] | None = None,
) -> ProviderStatusReport:
    spec_list = list(specs)
    if provider_filter:
        by_id = {spec.provider_id: spec for spec in spec_list}
        if provider_filter not in by_id:
            raise ValueError(f"Unknown provider: {provider_filter}")
        spec_list = [by_id[provider_filter]]

    env = environ if environ is not None else os.environ
    active = active_llm_provider(provider_selector, config)
    llm_cfg = getattr(config, "llm", None)
    rows: list[ProviderStatusRow] = []
    for spec in spec_list:
        is_active = spec.provider_id == active
        api_key_configured = _provider_key_configured(spec, is_active, llm_cfg, env)
        base_url = _provider_base_url(spec, is_active, llm_cfg)
        base_url_configured = bool(base_url)
        configured = (
            spec.runtime_supported
            and (not spec.requires_api_key or api_key_configured)
            and (not spec.requires_base_url or base_url_configured)
        )
        model = str(getattr(llm_cfg, "model", "") or "") if is_active else ""
        buildable, error = _provider_buildability(spec, is_active, model, llm_cfg, base_url)
        probe = (
            await probe_provider_models(spec.provider_id, provider_selector)
            if probe_models and is_active
            else ProviderModelProbe(
                attempted=False,
                status="skipped",
                count=0,
                error=None,
            )
        )
        rows.append(
            ProviderStatusRow(
                provider_id=spec.provider_id,
                active=is_active,
                configured=configured,
                buildable=buildable,
                model=model,
                requires_api_key=spec.requires_api_key,
                api_key_configured=api_key_configured,
                base_url_configured=base_url_configured,
                error=error,
                model_probe=probe,
            )
        )
    return ProviderStatusReport(active_provider=active, rows=tuple(rows))


def active_llm_provider(provider_selector: Any | None, config: Any | None) -> str | None:
    current_config = getattr(provider_selector, "current_config", None)
    provider = getattr(current_config, "provider", None)
    if provider:
        return str(provider)
    llm_cfg = getattr(config, "llm", None)
    provider = getattr(llm_cfg, "provider", None)
    return str(provider) if provider else None


async def probe_provider_models(
    provider_id: str,
    provider_selector: Any | None,
) -> ProviderModelProbe:
    if provider_selector is None:
        return ProviderModelProbe(
            attempted=True,
            status="unavailable",
            count=0,
            error="No provider selector configured",
        )
    try:
        models = await provider_selector.list_models()
    except Exception as exc:  # noqa: BLE001 - diagnostic surface
        return ProviderModelProbe(
            attempted=True,
            status="error",
            count=0,
            error=str(exc),
        )

    count = sum(
        1
        for model in models or []
        if str(_model_payload(model).get("provider") or "") == provider_id
    )
    return ProviderModelProbe(attempted=True, status="ok", count=count, error=None)


def _provider_key_configured(
    spec: ProviderStatusSpec,
    is_active: bool,
    llm_cfg: Any | None,
    environ: Mapping[str, str],
) -> bool:
    if is_active and bool(getattr(llm_cfg, "api_key", "")):
        return True
    return bool(spec.env_key and environ.get(spec.env_key))


def _provider_base_url(
    spec: ProviderStatusSpec,
    is_active: bool,
    llm_cfg: Any | None,
) -> str:
    configured_base_url = getattr(llm_cfg, "base_url", None)
    if is_active and configured_base_url:
        return str(configured_base_url)
    return spec.default_base_url


def _provider_buildability(
    spec: ProviderStatusSpec,
    is_active: bool,
    model: str,
    llm_cfg: Any | None,
    base_url: str,
) -> tuple[bool, str | None]:
    try:
        build_provider(
            spec.provider_id,
            model or "diagnostic-model",
            api_key=str(getattr(llm_cfg, "api_key", "") or "") if is_active else "",
            base_url=base_url,
        )
        return True, None
    except ProviderBuildError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - diagnostic surface
        return False, str(exc)


def _model_payload(model: Any) -> dict[str, Any]:
    if isinstance(model, dict):
        return model
    model_dump = getattr(model, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}
