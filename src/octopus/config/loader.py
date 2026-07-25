"""Configuration loader — multi-layer resolution.

Resolution order (highest priority first):
1. CLI arguments
2. Environment variables (OCTOPUS_*)
3. Config file (~/.octopus/settings.yaml)
4. Project config (.octopus/config.yaml)
5. Defaults (in Pydantic models)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from octopus.config.schema import OctopusSettings


def load_settings(
    *,
    cli_overrides: dict[str, Any] | None = None,
    config_path: Path | None = None,
    project_path: Path | None = None,
) -> OctopusSettings:
    """Load settings with multi-layer resolution."""
    data: dict[str, Any] = {}

    # Layer 4: Project config
    if project_path:
        project_config = _load_yaml(project_path / ".octopus" / "config.yaml")
        if project_config:
            _deep_merge(data, project_config)

    # Layer 3: User config file
    user_config_path = config_path or (Path.home() / ".octopus" / "settings.yaml")
    user_config = _load_yaml(user_config_path)
    if user_config:
        _deep_merge(data, user_config)

    # Layer 2: Environment variables
    env_overrides = _load_env()
    if env_overrides:
        _deep_merge(data, env_overrides)

    # Layer 1: CLI overrides
    if cli_overrides:
        _deep_merge(data, cli_overrides)

    # Ensure default providers exist
    _ensure_default_providers(data)

    return OctopusSettings(**data)


def save_settings(settings: OctopusSettings, path: Path | None = None) -> None:
    """Save settings to YAML file."""
    path = path or (Path.home() / ".octopus" / "settings.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = settings.model_dump()
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load a YAML file if it exists."""
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        return yaml.safe_load(content) or {}
    except Exception:
        return None


def _load_env() -> dict[str, Any]:
    """Load settings from environment variables."""
    data: dict[str, Any] = {}

    # Provider settings
    if api_key := os.environ.get("OCTOPUS_API_KEY"):
        data.setdefault("providers", [])
        # Add/update the default provider with the API key
        found = False
        for p in data["providers"]:
            if p.get("name") == data.get("default_provider", "claude"):
                p["api_key"] = api_key
                found = True
                break
        if not found:
            data["providers"].append(
                {
                    "name": "claude",
                    "provider": "anthropic",
                    "api_key": api_key,
                }
            )

    if model := os.environ.get("OCTOPUS_MODEL"):
        data["default_model"] = model

    if mode := os.environ.get("OCTOPUS_PERMISSION_MODE"):
        data.setdefault("permissions", {})["mode"] = mode

    return data


def _ensure_default_providers(data: dict[str, Any]) -> None:
    """Ensure default provider profiles exist."""
    providers = data.get("providers", [])
    names = {p.get("name") for p in providers}

    # Add default Claude provider if not present
    if "claude" not in names:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
            "OCTOPUS_API_KEY"
        )
        providers.append(
            {
                "name": "claude",
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "api_key": api_key,
            }
        )

    # Add default OpenAI provider if not present
    if "openai" not in names:
        api_key = os.environ.get("OPENAI_API_KEY")
        providers.append(
            {
                "name": "openai",
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": api_key,
            }
        )

    data["providers"] = providers


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Deep merge overlay into base (mutates base)."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
