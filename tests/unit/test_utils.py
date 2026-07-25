"""Tests for octopus.utils — file operations and platform detection."""

from __future__ import annotations

import pytest
from pathlib import Path

from octopus.utils.files import atomic_write, file_lock
from octopus.utils.platform import get_platform, is_linux, is_macos, is_windows


class TestAtomicWrite:
    def test_write_string(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"
        atomic_write(path, "hello world")
        assert path.read_text() == "hello world"

    def test_write_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "test.bin"
        atomic_write(path, b"\x00\x01\x02")
        assert path.read_bytes() == b"\x00\x01\x02"

    def test_write_creates_parents(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "file.txt"
        atomic_write(path, "nested")
        assert path.read_text() == "nested"

    def test_write_overwrites(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"
        atomic_write(path, "old")
        atomic_write(path, "new")
        assert path.read_text() == "new"


class TestFileLock:
    def test_basic_lock(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "test.lock"
        with file_lock(lock_path):
            assert lock_path.exists()

    def test_lock_creates_parent_dirs(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "sub" / "dir" / "test.lock"
        with file_lock(lock_path):
            assert lock_path.exists()


class TestPlatform:
    def test_get_platform(self) -> None:
        info = get_platform()
        assert info.os in ("linux", "macos", "windows")
        assert info.arch in ("x86_64", "arm64", "aarch64", "AMD64", "x86")
        assert info.python_version
        assert info.shell

    def test_os_detection(self) -> None:
        # At least one should be true
        assert is_linux() or is_macos() or is_windows()

    def test_linux_on_ci(self) -> None:
        # Most CI runs on Linux
        info = get_platform()
        if info.os == "linux":
            assert is_linux()
