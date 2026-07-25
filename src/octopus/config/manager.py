"""Configuration manager — reads auth.json and config.toml from ~/.octopus/.

File layout:
    ~/.octopus/auth.json    — API keys (sensitive, never committed)
    ~/.octopus/config.toml  — Model/provider settings

auth.json format:
    {
        "OPENAI_API_KEY": "sk-...",
        "ANTHROPIC_API_KEY": "sk-ant-..."
    }

config.toml format:
    model_provider = "custom"
    model = "gpt-4o"
    model_reasoning_effort = "high"

    [model_providers.custom]
    name = "Custom Provider"
    base_url = "https://api.example.com/v1"
    wire_api = "chat_completions"
    requires_openai_auth = true
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """Return ~/.octopus/ directory, creating it if needed."""
    d = Path.home() / ".octopus"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _auth_path() -> Path:
    return _config_dir() / "auth.json"


def _config_path() -> Path:
    return _config_dir() / "config.toml"


# ---------------------------------------------------------------------------
# Auth (auth.json)
# ---------------------------------------------------------------------------


@dataclass
class AuthConfig:
    """API keys loaded from auth.json."""

    keys: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        return self.keys.get(key)

    @property
    def openai_api_key(self) -> str | None:
        return self.get("OPENAI_API_KEY")

    @property
    def anthropic_api_key(self) -> str | None:
        return self.get("ANTHROPIC_API_KEY")


def load_auth() -> AuthConfig:
    """Load API keys from auth.json. Returns empty config if file missing."""
    path = _auth_path()
    if not path.exists():
        return AuthConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return AuthConfig(keys=data)
    except (json.JSONDecodeError, OSError):
        pass
    return AuthConfig()


def save_auth(auth: AuthConfig) -> None:
    """Save API keys to auth.json with 0o600 permissions."""
    path = _auth_path()
    path.write_text(
        json.dumps(auth.keys, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


# ---------------------------------------------------------------------------
# Config (config.toml)
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """A single model provider configuration."""

    name: str = ""
    base_url: str = ""
    wire_api: str = "chat_completions"  # "chat_completions" or "responses"
    requires_openai_auth: bool = False


@dataclass
class OctopusConfig:
    """Main configuration loaded from config.toml."""

    model_provider: str = ""
    model: str = ""
    model_reasoning_effort: str = "high"
    model_providers: dict[str, ProviderConfig] = field(default_factory=dict)

    # Raw dict for any extra fields
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def provider_config(self) -> ProviderConfig | None:
        """Get the active provider configuration."""
        if self.model_provider and self.model_provider in self.model_providers:
            return self.model_providers[self.model_provider]
        return None


def _parse_toml_simple(text: str) -> dict[str, Any]:
    """Minimal TOML parser for flat keys and [section] tables.

    Handles:
        key = "value"
        key = true
        key = 123
        [section]
        [section.subsection]
    """
    import re

    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Section header: [a.b.c]
        section_match = re.match(r"^\[([^\]]+)\]$", line)
        if section_match:
            parts = section_match.group(1).split(".")
            # Navigate to the section, creating as needed
            target = result
            for part in parts:
                if part not in target:
                    target[part] = {}
                target = target[part]
            current_section = target
            continue

        # Key = value
        kv_match = re.match(r"^(\w+)\s*=\s*(.+)$", line)
        if kv_match:
            key = kv_match.group(1)
            raw_value = kv_match.group(2).strip()

            # Parse value
            if raw_value.startswith('"') and raw_value.endswith('"'):
                value: Any = raw_value[1:-1]
            elif raw_value in ("true", "True"):
                value = True
            elif raw_value in ("false", "False"):
                value = False
            else:
                try:
                    value = int(raw_value)
                except ValueError:
                    try:
                        value = float(raw_value)
                    except ValueError:
                        value = raw_value

            if current_section is not None:
                current_section[key] = value
            else:
                result[key] = value

    return result


def _dict_to_provider(name: str, data: dict[str, Any]) -> ProviderConfig:
    """Convert a dict to ProviderConfig."""
    return ProviderConfig(
        name=data.get("name", name),
        base_url=data.get("base_url", ""),
        wire_api=data.get("wire_api", "chat_completions"),
        requires_openai_auth=data.get("requires_openai_auth", False),
    )


def load_config() -> OctopusConfig:
    """Load configuration from config.toml. Returns defaults if missing."""
    path = _config_path()
    if not path.exists():
        return OctopusConfig()

    try:
        text = path.read_text(encoding="utf-8")
        raw = _parse_toml_simple(text)
    except OSError:
        return OctopusConfig()

    # Extract top-level fields
    config = OctopusConfig(
        model_provider=raw.get("model_provider", ""),
        model=raw.get("model", ""),
        model_reasoning_effort=raw.get("model_reasoning_effort", "high"),
    )

    # Extract providers
    providers_raw = raw.get("model_providers", {})
    if isinstance(providers_raw, dict):
        for name, provider_data in providers_raw.items():
            if isinstance(provider_data, dict):
                config.model_providers[name] = _dict_to_provider(name, provider_data)

    return config


def save_config(config: OctopusConfig) -> None:
    """Save configuration to config.toml."""
    path = _config_path()

    lines: list[str] = []
    lines.append(f'model_provider = "{config.model_provider}"')
    lines.append(f'model = "{config.model}"')
    lines.append(f'model_reasoning_effort = "{config.model_reasoning_effort}"')
    lines.append("")

    for name, provider in config.model_providers.items():
        lines.append(f"[model_providers.{name}]")
        lines.append(f'name = "{provider.name}"')
        lines.append(f'base_url = "{provider.base_url}"')
        lines.append(f'wire_api = "{provider.wire_api}"')
        lines.append(
            f"requires_openai_auth = {str(provider.requires_openai_auth).lower()}"
        )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def get_active_model() -> str | None:
    """Get the configured model name, or None if not set."""
    config = load_config()
    return config.model if config.model else None


def get_active_provider() -> str | None:
    """Get the active provider name, or None if not set."""
    config = load_config()
    return config.model_provider if config.model_provider else None


def get_api_key_for_provider(provider: str) -> str | None:
    """Get the API key for a given provider."""
    auth = load_auth()

    # Try provider-specific key first, then generic OPENAI_API_KEY
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }

    key_name = key_map.get(provider.lower(), "OPENAI_API_KEY")
    return auth.get(key_name) or auth.openai_api_key
