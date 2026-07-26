"""Workspace trust management.

Inspired by MiMo-Code's workspace trust system. When entering an
unfamiliar directory, the user is prompted to trust or not trust the
workspace. Trust levels affect permission behavior:

- trusted:   Normal permissions as configured
- untrusted: Stricter — all mutations require approval
- dangerous: Home/root directories — blocked entirely

Trusted workspaces are stored in ~/.octopus/trusted-workspaces.json.
"""

from __future__ import annotations

import json
from pathlib import Path

TrustLevel = str  # "trusted" | "untrusted" | "dangerous"

_STORE_FILE = Path.home() / ".octopus" / "trusted-workspaces.json"


def _read_store() -> list[str]:
    """Read the trusted workspace paths from disk."""
    if not _STORE_FILE.exists():
        return []
    try:
        data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("trusted_paths", [])
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _write_store(paths: list[str]) -> None:
    """Write trusted workspace paths to disk."""
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STORE_FILE.write_text(
        json.dumps({"version": 1, "trusted_paths": paths}, indent=2) + "\n",
        encoding="utf-8",
    )


def check_trust(directory: str) -> TrustLevel:
    """Check the trust level of a directory.

    Returns:
        "trusted"   — previously trusted by user
        "untrusted" — not yet trusted, needs user confirmation
        "dangerous" — home directory or root (blocked)
    """
    normalized = str(Path(directory).resolve())
    home = str(Path.home().resolve())
    root = str(Path(normalized).anchor)

    # Home or root — dangerous, never auto-trust
    if normalized == home or normalized == root:
        return "dangerous"

    # Check if directory is under a trusted path
    trusted_paths = _read_store()
    for trusted in trusted_paths:
        if normalized == trusted or normalized.startswith(trusted + "/"):
            return "trusted"

    return "untrusted"


def mark_trusted(directory: str) -> None:
    """Mark a directory as trusted."""
    normalized = str(Path(directory).resolve())
    trusted_paths = _read_store()
    if normalized not in trusted_paths:
        trusted_paths.append(normalized)
        _write_store(trusted_paths)


def revoke_trust(directory: str) -> None:
    """Revoke trust for a directory."""
    normalized = str(Path(directory).resolve())
    trusted_paths = _read_store()
    _write_store([p for p in trusted_paths if p != normalized])


def list_trusted() -> list[str]:
    """List all trusted workspaces."""
    return _read_store()
