"""Tests for octopus.auth — CredentialStore."""

from __future__ import annotations

import pytest
from pathlib import Path

from octopus.auth.credentials import CredentialStore


@pytest.fixture
def cred_store(tmp_path: Path) -> CredentialStore:
    """Create a CredentialStore with a temporary path."""
    return CredentialStore(path=tmp_path / "creds.enc")


class TestCredentialStore:
    def test_store_and_retrieve(self, cred_store: CredentialStore) -> None:
        cred_store.store("api_key", "sk-ant-12345")
        assert cred_store.retrieve("api_key") == "sk-ant-12345"

    def test_retrieve_nonexistent(self, cred_store: CredentialStore) -> None:
        assert cred_store.retrieve("nonexistent") is None

    def test_delete(self, cred_store: CredentialStore) -> None:
        cred_store.store("key", "value")
        assert cred_store.delete("key")
        assert cred_store.retrieve("key") is None

    def test_delete_nonexistent(self, cred_store: CredentialStore) -> None:
        assert not cred_store.delete("nonexistent")

    def test_list_keys(self, cred_store: CredentialStore) -> None:
        cred_store.store("key1", "val1")
        cred_store.store("key2", "val2")
        keys = cred_store.list_keys()
        assert "key1" in keys
        assert "key2" in keys

    def test_overwrite(self, cred_store: CredentialStore) -> None:
        cred_store.store("key", "old")
        cred_store.store("key", "new")
        assert cred_store.retrieve("key") == "new"

    def test_file_permissions(self, cred_store: CredentialStore) -> None:
        cred_store.store("key", "value")
        mode = oct(cred_store._path.stat().st_mode)[-3:]
        assert mode == "600"

    def test_multiple_credentials(self, cred_store: CredentialStore) -> None:
        cred_store.store("anthropic", "sk-ant-xxx")
        cred_store.store("openai", "sk-yyy")
        cred_store.store("github", "ghp_zzz")

        assert cred_store.retrieve("anthropic") == "sk-ant-xxx"
        assert cred_store.retrieve("openai") == "sk-yyy"
        assert cred_store.retrieve("github") == "ghp_zzz"
        assert len(cred_store.list_keys()) == 3
