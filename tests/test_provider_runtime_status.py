from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from opensquilla.provider.runtime_status import build_provider_status_report


@dataclass(frozen=True)
class FakeStatusSpec:
    provider_id: str
    runtime_supported: bool = True
    env_key: str = "OPENROUTER_API_KEY"
    default_base_url: str = "https://openrouter.ai/api/v1"
    requires_api_key: bool = True
    requires_base_url: bool = False


class FailingModelSelector:
    current_config = SimpleNamespace(provider="openrouter")

    async def list_models(self) -> list[dict[str, object]]:
        raise RuntimeError("catalog unavailable")


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
async def test_build_provider_status_report_resolves_configured_active_provider() -> None:
    report = await build_provider_status_report(
        [FakeStatusSpec(provider_id="openrouter")],
        provider_selector=None,
        config=_config(api_key="secret-key", base_url="https://custom.example/v1"),
        environ={},
    )

    assert report.active_provider == "openrouter"
    row = report.rows[0]
    assert row.active is True
    assert row.configured is True
    assert row.buildable is True
    assert row.model == "openrouter/model"
    assert row.api_key_configured is True
    assert row.base_url_configured is True
    assert row.model_probe.status == "skipped"
    assert "secret-key" not in repr(report)


@pytest.mark.asyncio
async def test_build_provider_status_report_filters_and_raises_unknown_provider() -> None:
    report = await build_provider_status_report(
        [
            FakeStatusSpec(provider_id="openrouter"),
            FakeStatusSpec(provider_id="ollama", env_key="", requires_api_key=False),
        ],
        provider_selector=None,
        config=_config(),
        provider_filter="ollama",
        environ={},
    )

    assert [row.provider_id for row in report.rows] == ["ollama"]
    with pytest.raises(ValueError, match="Unknown provider"):
        await build_provider_status_report(
            [FakeStatusSpec(provider_id="openrouter")],
            provider_selector=None,
            config=_config(),
            provider_filter="missing",
            environ={},
        )


@pytest.mark.asyncio
async def test_build_provider_status_report_probes_selector_errors() -> None:
    report = await build_provider_status_report(
        [FakeStatusSpec(provider_id="openrouter")],
        provider_selector=FailingModelSelector(),
        config=_config(),
        probe_models=True,
        environ={"OPENROUTER_API_KEY": "from-env"},
    )

    probe = report.rows[0].model_probe
    assert probe.attempted is True
    assert probe.status == "error"
    assert probe.count == 0
    assert probe.error == "catalog unavailable"
