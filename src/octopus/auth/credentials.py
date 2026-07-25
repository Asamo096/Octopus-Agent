"""Credential store — encrypted file-based credential storage.

Uses Fernet symmetric encryption (from the 'cryptography' package) with
a key derived from machine-specific data. Credentials are stored in
~/.octopus/credentials.enc with POSIX mode 0o600.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

# Default credentials file
DEFAULT_CREDENTIALS_PATH = Path.home() / ".octopus" / "credentials.enc"

# Fallback encryption key derivation (when cryptography is not available)
_FALLBACK_KEY = "octopus-fallback-key-not-secure"


class CredentialStore:
    """Encrypted file-based credential storage.

    Usage:
        store = CredentialStore()
        store.store("anthropic_api_key", "sk-ant-...")
        key = store.retrieve("anthropic_api_key")
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_CREDENTIALS_PATH
        self._fernet = None
        self._init_encryption()

    def _init_encryption(self) -> None:
        """Initialize Fernet encryption if available."""
        try:
            from cryptography.fernet import Fernet  # type: ignore[import-not-found]

            key = self._derive_key()
            self._fernet = Fernet(key)
        except ImportError:
            logger.warning(
                "cryptography package not installed. "
                "Credentials will be stored as base64-encoded plaintext. "
                "Install with: pip install cryptography"
            )

    def _derive_key(self) -> bytes:
        """Derive an encryption key from machine-specific data."""
        # Combine machine-specific data
        machine_data = "|".join(
            [
                platform.node(),
                platform.machine(),
                str(os.getuid()) if hasattr(os, "getuid") else "windows",
                os.environ.get("USER", os.environ.get("USERNAME", "default")),
            ]
        )

        # Hash to create a deterministic key
        key_material = hashlib.sha256(machine_data.encode()).digest()

        # Fernet requires a 32-byte base64-encoded key
        import base64

        return base64.urlsafe_b64encode(key_material)

    def store(self, key: str, value: str) -> None:
        """Store a credential.

        Args:
            key: Credential key (e.g., "anthropic_api_key")
            value: Credential value (e.g., "sk-ant-...")
        """
        # Load existing credentials
        credentials = self._load_all()
        credentials[key] = value

        # Encrypt and save
        data = json.dumps(credentials).encode()
        if self._fernet:
            encrypted = self._fernet.encrypt(data)
        else:
            # Fallback: base64 encode (NOT secure)
            import base64

            encrypted = base64.b64encode(data)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(encrypted)
        self._path.chmod(0o600)
        logger.debug("Stored credential: %s", key)

    def retrieve(self, key: str) -> str | None:
        """Retrieve a credential.

        Args:
            key: Credential key

        Returns:
            The credential value, or None if not found
        """
        credentials = self._load_all()
        return credentials.get(key)

    def delete(self, key: str) -> bool:
        """Delete a credential.

        Args:
            key: Credential key

        Returns:
            True if deleted, False if not found
        """
        credentials = self._load_all()
        if key not in credentials:
            return False

        del credentials[key]

        # Re-encrypt and save
        data = json.dumps(credentials).encode()
        if self._fernet:
            encrypted = self._fernet.encrypt(data)
        else:
            import base64

            encrypted = base64.b64encode(data)

        self._path.write_bytes(encrypted)
        self._path.chmod(0o600)
        logger.debug("Deleted credential: %s", key)
        return True

    def list_keys(self) -> list[str]:
        """List all credential keys (without values)."""
        return list(self._load_all().keys())

    def _load_all(self) -> dict[str, str]:
        """Load and decrypt all credentials."""
        if not self._path.exists():
            return {}

        try:
            encrypted = self._path.read_bytes()
            if self._fernet:
                decrypted = self._fernet.decrypt(encrypted)
            else:
                import base64

                decrypted = base64.b64decode(encrypted)

            result: dict[str, str] = json.loads(decrypted)
            return result
        except Exception as e:
            logger.error("Failed to load credentials: %s", e)
            return {}
