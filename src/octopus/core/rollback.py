"""Task rollback engine — checkpoint and restore file state.

The rollback engine snapshots file content before each tool call via
the PreToolUse hook, enabling one-click restoration to any previous state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass
class Checkpoint:
    """A rollback checkpoint."""

    id: str
    session_id: str
    tool_name: str
    tool_args: dict[str, Any]
    created_at: datetime
    files: list[FileSnapshot]


@dataclass
class FileSnapshot:
    """A snapshot of a single file."""

    path: str
    content_hash: str
    content: str | None  # None if file didn't exist (new file checkpoint)
    existed: bool


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS checkpoints (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name  TEXT NOT NULL,
    tool_args  TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoint_files (
    checkpoint_id TEXT NOT NULL REFERENCES checkpoints(id),
    file_path     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    content       TEXT,
    existed       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (checkpoint_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_session ON checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_time    ON checkpoints(created_at);
"""


class RollbackEngine:
    """Checkpoint and restore file state."""

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(str(self._db_path))
            await self._db.executescript(_SCHEMA_SQL)
            await self._db.commit()
        return self._db

    # ---- checkpoint -------------------------------------------------------

    async def checkpoint(
        self,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        affected_paths: list[Path],
    ) -> str:
        """Create a checkpoint before a tool modifies files.

        Returns the checkpoint ID.
        """
        import uuid

        db = await self._ensure_db()
        checkpoint_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        # Snapshot files
        snapshots: list[FileSnapshot] = []
        for path in affected_paths:
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="replace")
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                snapshots.append(
                    FileSnapshot(
                        path=str(path),
                        content_hash=content_hash,
                        content=content,
                        existed=True,
                    )
                )
            else:
                snapshots.append(
                    FileSnapshot(
                        path=str(path),
                        content_hash="missing",
                        content=None,
                        existed=False,
                    )
                )

        # Insert checkpoint
        await db.execute(
            "INSERT INTO checkpoints (id, session_id, tool_name, tool_args, created_at) VALUES (?, ?, ?, ?, ?)",
            (checkpoint_id, session_id, tool_name, json.dumps(tool_args), now),
        )

        # Insert file snapshots
        for snap in snapshots:
            await db.execute(
                "INSERT INTO checkpoint_files (checkpoint_id, file_path, content_hash, content, existed) VALUES (?, ?, ?, ?, ?)",
                (
                    checkpoint_id,
                    snap.path,
                    snap.content_hash,
                    snap.content,
                    int(snap.existed),
                ),
            )

        await db.commit()
        return checkpoint_id

    # ---- restore ----------------------------------------------------------

    async def restore(self, checkpoint_id: str) -> list[str]:
        """Restore files to a checkpoint state.

        Returns a list of restored file paths.
        """
        db = await self._ensure_db()

        # Load file snapshots
        cursor = await db.execute(
            "SELECT file_path, content, existed FROM checkpoint_files WHERE checkpoint_id = ?",
            (checkpoint_id,),
        )
        rows = await cursor.fetchall()

        if not rows:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        restored: list[str] = []
        for file_path, content, existed in rows:
            path = Path(file_path)

            if not existed:
                # File didn't exist at checkpoint — delete it if it exists now
                if path.exists():
                    path.unlink()
                    restored.append(f"deleted: {file_path}")
            else:
                # File existed — restore content
                path.parent.mkdir(parents=True, exist_ok=True)
                if content is not None:
                    path.write_text(content, encoding="utf-8")
                    restored.append(f"restored: {file_path}")

        return restored

    # ---- query ------------------------------------------------------------

    async def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """List all checkpoints for a session."""
        db = await self._ensure_db()

        cursor = await db.execute(
            "SELECT id, tool_name, tool_args, created_at FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        )
        rows = await cursor.fetchall()

        checkpoints: list[Checkpoint] = []
        for row in rows:
            cp_id, tool_name, tool_args_str, created_at = row

            # Load files
            file_cursor = await db.execute(
                "SELECT file_path, content_hash, existed FROM checkpoint_files WHERE checkpoint_id = ?",
                (cp_id,),
            )
            file_rows = await file_cursor.fetchall()
            files = [
                FileSnapshot(
                    path=r[0], content_hash=r[1], content=None, existed=bool(r[2])
                )
                for r in file_rows
            ]

            checkpoints.append(
                Checkpoint(
                    id=cp_id,
                    session_id=session_id,
                    tool_name=tool_name,
                    tool_args=json.loads(tool_args_str),
                    created_at=datetime.fromisoformat(created_at),
                    files=files,
                )
            )

        return checkpoints

    async def diff_checkpoint(self, checkpoint_id: str) -> str:
        """Show the diff between a checkpoint and current state."""
        import difflib

        db = await self._ensure_db()

        cursor = await db.execute(
            "SELECT file_path, content, existed FROM checkpoint_files WHERE checkpoint_id = ?",
            (checkpoint_id,),
        )
        rows = await cursor.fetchall()

        diffs: list[str] = []
        for file_path, old_content, existed in rows:
            path = Path(file_path)

            if not existed:
                if path.exists():
                    new_content = path.read_text(encoding="utf-8", errors="replace")
                    diff = difflib.unified_diff(
                        [],
                        new_content.splitlines(keepends=True),
                        fromfile="/dev/null",
                        tofile=f"b/{file_path}",
                    )
                    diffs.append("".join(diff))
            else:
                if path.exists():
                    new_content = path.read_text(encoding="utf-8", errors="replace")
                    if old_content != new_content:
                        diff = difflib.unified_diff(
                            old_content.splitlines(keepends=True),
                            new_content.splitlines(keepends=True),
                            fromfile=f"a/{file_path}",
                            tofile=f"b/{file_path}",
                        )
                        diffs.append("".join(diff))
                else:
                    diff = difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        [],
                        fromfile=f"a/{file_path}",
                        tofile="/dev/null",
                    )
                    diffs.append("".join(diff))

        return "\n".join(diffs) if diffs else "No changes since checkpoint."

    # ---- lifecycle --------------------------------------------------------

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
