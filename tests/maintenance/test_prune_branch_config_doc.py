"""The prune doc of record must match the rollback, lock, and exit code behavior.

PR #6705 changed ``--apply`` rollback and added ``config.prune-lock`` but left
``docs/troubleshooting-branch-config.md`` describing the old whole-file restore.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parents[2] / "docs" / "troubleshooting-branch-config.md"


@pytest.fixture(scope="module")
def doc() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


class TestRollbackText:
    def test_describes_section_only_restore(self, doc: str) -> None:
        assert "only the sections this run removed are written back" in doc

    def test_describes_whole_file_fallback_when_config_unparseable(self, doc: str) -> None:
        assert "no longer parses, the whole backup is copied back" in doc

    def test_describes_readable_config_left_in_place(self, doc: str) -> None:
        assert "the live file is left in place" in doc

    def test_drops_stale_blanket_restore_claim(self, doc: str) -> None:
        assert "On any failure it restores the copy." not in doc


class TestLockText:
    def test_names_lock_file(self, doc: str) -> None:
        assert "config.prune-lock" in doc

    def test_says_killed_prune_leaves_lock(self, doc: str) -> None:
        assert "killed" in doc and "leaves it behind" in doc

    def test_exit_3_covers_held_lock(self, doc: str) -> None:
        exit3 = re.search(r"Exit codes:.*?`3` (.*?\.(?: |$))", doc)
        assert exit3 is not None
        assert "holds `config.prune-lock`" in exit3.group(1)

    def test_exit_3_still_covers_git_failure(self, doc: str) -> None:
        assert "git failed or timed out" in doc
