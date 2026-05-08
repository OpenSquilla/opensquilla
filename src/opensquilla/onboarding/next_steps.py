"""Secret-safe next-step text for onboarding output."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from opensquilla.onboarding.status import get_onboarding_status

_KEY_URLS = {
    "openrouter": "https://openrouter.ai/keys",
    "openai": "https://platform.openai.com/api-keys",
    "anthropic": "https://console.anthropic.com/settings/keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
}


def _set_env_hint(env_key: str) -> str:
    if platform.system().lower().startswith("win"):
        return f'PowerShell: $env:{env_key} = "<your-key>"'
    return f'export {env_key}="<your-key>"'


def format_next_steps(config: Any, *, config_path: str | Path | None = None) -> str:
    status = get_onboarding_status(config)
    llm = config.llm
    router = config.squilla_router
    path = str(config_path or status.config_path or getattr(config, "config_path", ""))
    provider = str(getattr(llm, "provider", "") or "")
    model = str(getattr(llm, "model", "") or "")
    env_key = str(getattr(llm, "api_key_env", "") or "")
    key_source = status.llm_source
    if key_source == "env" and env_key:
        key_line = f"Key: ${env_key}"
    elif key_source == "missing_env" and env_key:
        key_line = f"Key: ${env_key} is not set in this shell"
    elif key_source == "explicit":
        key_line = "Key: stored in config"
    else:
        key_line = "Key: not required" if status.llm_configured else "Key: not configured"

    lines = [
        "Next steps:",
        f"  Config: {path}",
        f"  LLM: {provider} / {model}",
        f"  {key_line}",
        (
            "  Router: disabled"
            if not router.enabled
            else (
                f"  Router: profile={router.tier_profile or 'openrouter-mix'}, "
                f"default={router.default_tier}"
            )
        ),
        "  Start gateway: uv run opensquilla gateway start --json",
        "  If a gateway is already running, restart it so it loads this config.",
        "  Restart gateway: uv run opensquilla gateway restart --json",
        "  Web UI: http://127.0.0.1:18790/control/",
    ]
    if key_source == "missing_env" and env_key:
        lines.append(f"  Set key before starting gateway: {_set_env_hint(env_key)}")
    key_url = _KEY_URLS.get(provider)
    if key_url:
        lines.append(f"  Provider keys: {key_url}")
    return "\n".join(lines)
