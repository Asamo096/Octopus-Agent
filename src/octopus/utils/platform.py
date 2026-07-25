"""Platform detection — OS identification and capabilities."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass


@dataclass
class PlatformInfo:
    """Information about the current platform."""

    os: str  # "linux", "macos", "windows"
    arch: str  # "x86_64", "arm64", etc.
    python_version: str
    has_docker: bool
    has_kvm: bool
    shell: str  # Default shell path


def get_platform() -> PlatformInfo:
    """Detect the current platform and capabilities."""
    os_name = _detect_os()
    arch = platform.machine()

    return PlatformInfo(
        os=os_name,
        arch=arch,
        python_version=sys.version,
        has_docker=_check_docker(),
        has_kvm=_check_kvm(),
        shell=_default_shell(os_name),
    )


def is_linux() -> bool:
    """Check if running on Linux."""
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def _detect_os() -> str:
    """Detect the operating system."""
    if sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    else:
        return sys.platform


def _check_docker() -> bool:
    """Check if Docker is available."""
    import shutil

    return shutil.which("docker") is not None


def _check_kvm() -> bool:
    """Check if KVM is available (Linux only)."""
    if not is_linux():
        return False
    from pathlib import Path

    return Path("/dev/kvm").exists()


def _default_shell(os_name: str) -> str:
    """Get the default shell for the OS."""
    if os_name == "windows":
        return "powershell"
    import os

    return os.environ.get("SHELL", "/bin/bash")
