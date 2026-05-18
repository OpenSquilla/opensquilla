from __future__ import annotations

from pathlib import Path

import pytest

import opensquilla.cli.main as cli_main
from opensquilla.gateway.config import GatewayConfig


@pytest.mark.parametrize(
    ("agent_id", "expected_suffix"),
    [
        ("main", ()),
        ("ops", ("agents", "ops")),
    ],
)
def test_cli_dream_uses_configured_agent_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_id: str,
    expected_suffix: tuple[str, ...],
) -> None:
    configured_workspace = tmp_path / "configured workspace"
    cwd = tmp_path / "launch cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    cfg = GatewayConfig(workspace_dir=str(configured_workspace))
    monkeypatch.setattr(GatewayConfig, "load", classmethod(lambda cls, _path=None: cfg))

    dream = cli_main._build_cli_dream(agent_id, need_provider=False)

    assert dream.workspace == configured_workspace.joinpath(*expected_suffix)
    assert not (cwd / ".opensquilla").exists()
