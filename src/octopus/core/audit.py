"""Octopus Agent Audit — Async audit logger backed by SQLite.

Every tool call, file edit, shell execution, and permission decision is recorded
as a structured AuditEvent and persisted to a local SQLite database.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class AuditEvent:
    """A single audit record."""
    timestamp: datetime
    tool: str
    args: Dict[str, Any]
    result: Any
    duration: float
    permission_decision: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AuditFilters:
    """Filters for querying audit events."""
    tool: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 100


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS audit_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    tool              TEXT    NOT NULL,
    args              TEXT    NOT NULL,
    result            TEXT,
    duration          REAL,
    permission_decision TEXT,
    session_id        TEXT,
    user_id           TEXT,
    metadata          TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_tool      ON audit_events(tool);
CREATE INDEX IF NOT EXISTS idx_audit_session   ON audit_events(session_id);
"""


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Structured audit trail for all agent actions (async, SQLite-backed)."""

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        """Lazily open the database connection."""
        if self._db is None:
            self._db = await aiosqlite.connect(str(self._db_path))
            await self._db.executescript(_SCHEMA_SQL)
            await self._db.commit()
        return self._db

    # ---- write -------------------------------------------------------------

    async def log(self, event: AuditEvent) -> None:
        """Insert an audit event."""
        db = await self._ensure_db()
        await db.execute(
            """INSERT INTO audit_events
               (timestamp, tool, args, result, duration,
                permission_decision, session_id, user_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.timestamp.isoformat(),
                event.tool,
                json.dumps(event.args),
                json.dumps(event.result) if event.result is not None else None,
                event.duration,
                event.permission_decision,
                event.session_id,
                event.user_id,
                json.dumps(event.metadata) if event.metadata else None,
            ),
        )
        await db.commit()

    # ---- read --------------------------------------------------------------

    async def query(self, filters: Optional[AuditFilters] = None) -> List[AuditEvent]:
        """Query audit events with optional filters."""
        db = await self._ensure_db()
        filters = filters or AuditFilters()

        clauses: List[str] = ["1=1"]
        params: List[Any] = []

        if filters.tool:
            clauses.append("tool = ?")
            params.append(filters.tool)
        if filters.session_id:
            clauses.append("session_id = ?")
            params.append(filters.session_id)
        if filters.user_id:
            clauses.append("user_id = ?")
            params.append(filters.user_id)
        if filters.start_time:
            clauses.append("timestamp >= ?")
            params.append(filters.start_time.isoformat())
        if filters.end_time:
            clauses.append("timestamp <= ?")
            params.append(filters.end_time.isoformat())

        sql = f"SELECT * FROM audit_events WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC LIMIT ?"
        params.append(filters.limit)

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

        events: List[AuditEvent] = []
        for row in rows:
            events.append(AuditEvent(
                timestamp=datetime.fromisoformat(row[1]),
                tool=row[2],
                args=json.loads(row[3]),
                result=json.loads(row[4]) if row[4] else None,
                duration=row[5],
                permission_decision=row[6],
                session_id=row[7],
                user_id=row[8],
                metadata=json.loads(row[9]) if row[9] else None,
            ))
        return events

    async def get_recent(self, limit: int = 10) -> List[AuditEvent]:
        """Get the most recent audit events."""
        return await self.query(AuditFilters(limit=limit))

    async def get_by_tool(self, tool: str, limit: int = 100) -> List[AuditEvent]:
        """Get events filtered by tool name."""
        return await self.query(AuditFilters(tool=tool, limit=limit))

    async def get_by_session(self, session_id: str, limit: int = 100) -> List[AuditEvent]:
        """Get events filtered by session ID."""
        return await self.query(AuditFilters(session_id=session_id, limit=limit))

    # ---- export ------------------------------------------------------------

    async def export_json(self, output_path: Path, filters: Optional[AuditFilters] = None) -> None:
        """Export events to a JSON file."""
        events = await self.query(filters or AuditFilters(limit=10_000))
        data = {
            "export_time": datetime.now(timezone.utc).isoformat(),
            "event_count": len(events),
            "events": [asdict(e) for e in events],
        }
        output_path.write_text(json.dumps(data, indent=2, default=str))

    async def export_csv(self, output_path: Path, filters: Optional[AuditFilters] = None) -> None:
        """Export events to a CSV file."""
        events = await self.query(filters or AuditFilters(limit=10_000))
        headers = [
            "timestamp", "tool", "args", "result", "duration",
            "permission_decision", "session_id", "user_id", "metadata",
        ]
        with output_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for e in events:
                writer.writerow([
                    e.timestamp.isoformat(),
                    e.tool,
                    json.dumps(e.args),
                    json.dumps(e.result) if e.result else "",
                    e.duration,
                    e.permission_decision,
                    e.session_id or "",
                    e.user_id or "",
                    json.dumps(e.metadata) if e.metadata else "",
                ])

    # ---- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
