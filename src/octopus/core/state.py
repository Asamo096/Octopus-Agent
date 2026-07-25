"""Octopus Agent State — Async state manager backed by SQLite.

Manages sessions, configuration, and metadata.  Both GUI and CLI share the
same SQLite database, enabling cross-process state synchronization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """State for a single conversation session."""
    session_id: str
    name: str = ""
    start_time: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    user_id: Optional[str] = None
    workspace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    start_time    TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    user_id       TEXT,
    workspace     TEXT,
    context       TEXT NOT NULL DEFAULT '{}',
    metadata      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS kv_store (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------

class StateManager:
    """Global state manager backed by SQLite."""

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

    # ---- sessions ----------------------------------------------------------

    async def create_session(
        self,
        session_id: str,
        *,
        name: str = "",
        user_id: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> SessionState:
        """Create a new session and return it."""
        db = await self._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO sessions (id, name, start_time, last_activity, user_id, workspace) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, name, now, now, user_id, workspace),
        )
        await db.commit()
        return SessionState(
            session_id=session_id,
            name=name,
            start_time=datetime.fromisoformat(now),
            last_activity=datetime.fromisoformat(now),
            user_id=user_id,
            workspace=workspace,
        )

    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get a session by ID."""
        db = await self._ensure_db()
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    async def update_session(self, session_id: str, **kwargs: Any) -> None:
        """Update fields on a session."""
        db = await self._ensure_db()
        allowed = {"name", "user_id", "workspace", "context", "metadata"}
        updates: List[str] = []
        params: List[Any] = []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key in ("context", "metadata"):
                value = json.dumps(value)
            updates.append(f"{key} = ?")
            params.append(value)
        if not updates:
            return
        updates.append("last_activity = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(session_id)
        await db.execute(
            f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        db = await self._ensure_db()
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()

    async def list_sessions(self) -> List[SessionState]:
        """List all sessions, most recent first."""
        db = await self._ensure_db()
        cursor = await db.execute("SELECT * FROM sessions ORDER BY last_activity DESC")
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]

    # ---- key-value store (config / metadata) -------------------------------

    async def set_value(self, key: str, value: Any) -> None:
        """Set a key-value pair."""
        db = await self._ensure_db()
        await db.execute(
            "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        await db.commit()

    async def get_value(self, key: str, default: Any = None) -> Any:
        """Get a value by key."""
        db = await self._ensure_db()
        cursor = await db.execute("SELECT value FROM kv_store WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row is None:
            return default
        return json.loads(row[0])

    async def delete_value(self, key: str) -> None:
        """Delete a key-value pair."""
        db = await self._ensure_db()
        await db.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        await db.commit()

    async def list_values(self, prefix: str = "") -> Dict[str, Any]:
        """List all key-value pairs, optionally filtered by prefix."""
        db = await self._ensure_db()
        if prefix:
            cursor = await db.execute(
                "SELECT key, value FROM kv_store WHERE key LIKE ? ORDER BY key",
                (f"{prefix}%",),
            )
        else:
            cursor = await db.execute("SELECT key, value FROM kv_store ORDER BY key")
        rows = await cursor.fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

    # ---- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _row_to_session(row: Any) -> SessionState:
        """Convert a database row to a SessionState."""
        return SessionState(
            session_id=row[0],
            name=row[1],
            start_time=datetime.fromisoformat(row[2]),
            last_activity=datetime.fromisoformat(row[3]),
            user_id=row[4],
            workspace=row[5],
            context=json.loads(row[6]) if row[6] else {},
            metadata=json.loads(row[7]) if row[7] else {},
        )
