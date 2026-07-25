"""Tests for octopus.core.rollback — RollbackEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.rollback import RollbackEngine


@pytest.fixture
async def engine(tmp_path: Path):
    db_path = tmp_path / "rollback.db"
    eng = RollbackEngine(db_path=db_path)
    yield eng
    await eng.close()


class TestRollbackEngine:
    async def test_checkpoint_and_restore(
        self, engine: RollbackEngine, tmp_path: Path
    ) -> None:
        # Create a file
        f = tmp_path / "test.txt"
        f.write_text("original content")

        # Create checkpoint
        cp_id = await engine.checkpoint(
            session_id="s1",
            tool_name="write_file",
            tool_args={"path": "test.txt"},
            affected_paths=[f],
        )
        assert cp_id

        # Modify the file
        f.write_text("modified content")
        assert f.read_text() == "modified content"

        # Restore
        restored = await engine.restore(cp_id)
        assert len(restored) == 1
        assert f.read_text() == "original content"

    async def test_checkpoint_new_file(
        self, engine: RollbackEngine, tmp_path: Path
    ) -> None:
        # Checkpoint a file that doesn't exist yet
        f = tmp_path / "new.txt"
        cp_id = await engine.checkpoint(
            session_id="s1",
            tool_name="write_file",
            tool_args={"path": "new.txt"},
            affected_paths=[f],
        )

        # Create the file
        f.write_text("new content")

        # Restore — file should be deleted
        restored = await engine.restore(cp_id)
        assert len(restored) == 1
        assert not f.exists()

    async def test_checkpoint_preserves_multiple_files(
        self, engine: RollbackEngine, tmp_path: Path
    ) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")

        cp_id = await engine.checkpoint(
            session_id="s1",
            tool_name="edit_file",
            tool_args={},
            affected_paths=[f1, f2],
        )

        f1.write_text("changed A")
        f2.write_text("changed B")

        restored = await engine.restore(cp_id)
        assert len(restored) == 2
        assert f1.read_text() == "content A"
        assert f2.read_text() == "content B"

    async def test_list_checkpoints(
        self, engine: RollbackEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "f.txt"
        f.write_text("v1")

        await engine.checkpoint("s1", "write_file", {"path": "f.txt"}, [f])
        f.write_text("v2")
        await engine.checkpoint("s1", "write_file", {"path": "f.txt"}, [f])

        cps = await engine.list_checkpoints("s1")
        assert len(cps) == 2
        # Most recent first
        assert cps[0].created_at >= cps[1].created_at

    async def test_diff_checkpoint(
        self, engine: RollbackEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "f.txt"
        f.write_text("line 1\nline 2\n")

        cp_id = await engine.checkpoint("s1", "write_file", {"path": "f.txt"}, [f])

        f.write_text("line 1\nline 2 modified\n")

        diff = await engine.diff_checkpoint(cp_id)
        assert "line 2 modified" in diff
        assert "+line 2 modified" in diff

    async def test_diff_checkpoint_no_changes(
        self, engine: RollbackEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "f.txt"
        f.write_text("same")

        cp_id = await engine.checkpoint("s1", "write_file", {"path": "f.txt"}, [f])

        diff = await engine.diff_checkpoint(cp_id)
        assert "no changes" in diff.lower()

    async def test_restore_nonexistent_checkpoint(self, engine: RollbackEngine) -> None:
        with pytest.raises(ValueError, match="not found"):
            await engine.restore("nonexistent")
