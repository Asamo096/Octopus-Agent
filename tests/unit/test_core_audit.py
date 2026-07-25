"""Tests for octopus.core.audit — AuditLogger."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from octopus.core.audit import AuditEvent, AuditFilters, AuditLogger


@pytest.fixture
async def audit(tmp_path: Path):
    """Provide an AuditLogger with a temporary database."""
    db_path = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db_path)
    yield logger
    await logger.close()


class TestAuditLogger:
    async def test_log_and_query(self, audit: AuditLogger) -> None:
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            tool="read_file",
            args={"path": "/tmp/test.py"},
            result={"output": "file contents"},
            duration=0.05,
            permission_decision="ALLOWED",
            session_id="s1",
        )
        await audit.log(event)

        events = await audit.query(AuditFilters(tool="read_file"))
        assert len(events) >= 1
        assert events[0].tool == "read_file"
        assert events[0].permission_decision == "ALLOWED"

    async def test_query_by_session(self, audit: AuditLogger) -> None:
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            tool="shell",
            args={"command": "ls"},
            result=None,
            duration=0.1,
            permission_decision="ALLOWED",
            session_id="session-abc",
        )
        await audit.log(event)

        events = await audit.get_by_session("session-abc")
        assert len(events) >= 1
        assert events[0].session_id == "session-abc"

    async def test_query_by_tool(self, audit: AuditLogger) -> None:
        for tool_name in ("read_file", "write_file", "read_file"):
            await audit.log(
                AuditEvent(
                    timestamp=datetime.now(UTC),
                    tool=tool_name,
                    args={},
                    result=None,
                    duration=0.01,
                    permission_decision="ALLOWED",
                )
            )

        events = await audit.get_by_tool("read_file")
        assert all(e.tool == "read_file" for e in events)
        assert len(events) >= 2

    async def test_get_recent(self, audit: AuditLogger) -> None:
        for i in range(5):
            await audit.log(
                AuditEvent(
                    timestamp=datetime.now(UTC),
                    tool=f"tool_{i}",
                    args={"i": i},
                    result=None,
                    duration=0.01,
                    permission_decision="ALLOWED",
                )
            )

        recent = await audit.get_recent(limit=3)
        assert len(recent) == 3

    async def test_export_json(self, audit: AuditLogger, tmp_path: Path) -> None:
        await audit.log(
            AuditEvent(
                timestamp=datetime.now(UTC),
                tool="test_tool",
                args={"key": "value"},
                result="ok",
                duration=0.02,
                permission_decision="ALLOWED",
            )
        )

        out = tmp_path / "export.json"
        await audit.export_json(out)
        assert out.exists()
        content = out.read_text()
        assert "test_tool" in content

    async def test_export_csv(self, audit: AuditLogger, tmp_path: Path) -> None:
        await audit.log(
            AuditEvent(
                timestamp=datetime.now(UTC),
                tool="test_tool",
                args={},
                result=None,
                duration=0.01,
                permission_decision="ALLOWED",
            )
        )

        out = tmp_path / "export.csv"
        await audit.export_csv(out)
        assert out.exists()
        lines = out.read_text().strip().split("\n")
        assert len(lines) >= 2  # header + at least one event
