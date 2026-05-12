from __future__ import annotations

import os
from pathlib import Path

from opensquilla.env import load_env


def test_load_env_strips_utf8_bom_from_first_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-test\n", encoding="utf-8-sig")

    injected = load_env(tmp_path)

    assert injected == 1
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"
    assert "\ufeffANTHROPIC_API_KEY" not in os.environ
