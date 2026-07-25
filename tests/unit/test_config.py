"""Tests for octopus.config — schema and loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from octopus.config.loader import load_settings
from octopus.config.schema import OctopusSettings, ProviderProfile


class TestOctopusSettings:
    def test_defaults(self) -> None:
        s = OctopusSettings()
        assert s.default_model == "claude-sonnet-4-20250514"
        assert s.permissions.mode == "default"
        assert s.sandbox.enabled is True
        assert s.cli.max_turns == 50

    def test_get_provider_by_name(self) -> None:
        s = OctopusSettings(
            providers=[
                ProviderProfile(
                    name="claude",
                    provider="anthropic",
                    model="claude-sonnet-4-20250514",
                ),
                ProviderProfile(name="openai", provider="openai", model="gpt-4o"),
            ]
        )
        p = s.get_provider("openai")
        assert p is not None
        assert p.model == "gpt-4o"

    def test_get_provider_default(self) -> None:
        s = OctopusSettings(
            providers=[
                ProviderProfile(name="claude", provider="anthropic"),
            ]
        )
        p = s.get_provider()
        assert p is not None
        assert p.name == "claude"

    def test_get_provider_not_found(self) -> None:
        s = OctopusSettings()
        p = s.get_provider("nonexistent")
        assert p is None


class TestLoadSettings:
    def test_load_from_file(self, tmp_path: Path) -> None:
        config = {
            "default_model": "gpt-4o",
            "permissions": {"mode": "full_auto"},
        }
        config_path = tmp_path / "settings.yaml"
        config_path.write_text(yaml.dump(config))

        settings = load_settings(config_path=config_path)
        assert settings.default_model == "gpt-4o"
        assert settings.permissions.mode == "full_auto"

    def test_load_defaults(self) -> None:
        # Load with no config file — should use defaults + env
        settings = load_settings(config_path=Path("/nonexistent/path"))
        assert settings.default_model == "claude-sonnet-4-20250514"
        assert len(settings.providers) >= 1  # At least default providers

    def test_project_config(self, tmp_path: Path) -> None:
        # Create project config
        octopus_dir = tmp_path / ".octopus"
        octopus_dir.mkdir()
        config = {"default_model": "local-model"}
        (octopus_dir / "config.yaml").write_text(yaml.dump(config))

        settings = load_settings(project_path=tmp_path)
        assert settings.default_model == "local-model"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OCTOPUS_MODEL", "env-model")
        settings = load_settings(config_path=Path("/nonexistent"))
        assert settings.default_model == "env-model"

    def test_cli_override(self) -> None:
        settings = load_settings(
            config_path=Path("/nonexistent"),
            cli_overrides={"default_model": "cli-model"},
        )
        assert settings.default_model == "cli-model"


class TestProviderProfile:
    def test_create(self) -> None:
        p = ProviderProfile(name="test", provider="openai", model="gpt-4o")
        assert p.name == "test"
        assert p.provider == "openai"
        assert p.model == "gpt-4o"

    def test_defaults(self) -> None:
        p = ProviderProfile(name="test")
        assert p.provider == "openai"
        assert p.api_format == "openai"
