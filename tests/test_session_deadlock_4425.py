"""Tests for the session-init/session-end deadlock fix (issue #4425).

The deadlock: _test_uncommitted_changes always returns True while the session
log is staged or modified, so changesCommitted can never be satisfied. The fix
excludes the session log path from the porcelain output before deciding.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock


def _import_target():
    import importlib
    import sys

    if "complete_session_log" in sys.modules:
        return sys.modules["complete_session_log"]
    spec = importlib.util.spec_from_file_location(
        "complete_session_log",
        Path(__file__).resolve().parents[1]
        / ".claude/skills/session-end/scripts/complete_session_log.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestUncommittedChangesExcludesSessionLog:
    """_test_uncommitted_changes must exclude the session log path (issue #4425)."""

    def _run(self, porcelain_output: str, exclude_path: str | None = None) -> bool:
        mod = _import_target()
        fake = subprocess.CompletedProcess([], 0, porcelain_output, "")
        with mock.patch("subprocess.run", return_value=fake):
            return mod._test_uncommitted_changes(exclude_path=exclude_path)

    def test_no_changes_returns_false(self) -> None:
        assert self._run("") is False

    def test_unrelated_dirty_file_returns_true(self) -> None:
        assert self._run(" M some/other/file.py") is True

    def test_session_log_only_returns_false_when_excluded(self) -> None:
        path = ".agents/sessions/2026-08-03-session-9999.json"
        porcelain = f" M {path}\n"
        assert self._run(porcelain, exclude_path=path) is False

    def test_session_log_without_exclude_returns_true(self) -> None:
        porcelain = " M .agents/sessions/2026-08-03-session-9999.json\n"
        assert self._run(porcelain, exclude_path=None) is True

    def test_session_log_plus_other_dirty_file_returns_true(self) -> None:
        path = ".agents/sessions/2026-08-03-session-9999.json"
        porcelain = f" M {path}\n M scripts/some_script.py\n"
        assert self._run(porcelain, exclude_path=path) is True

    def test_git_failure_returns_true(self) -> None:
        mod = _import_target()
        fake = subprocess.CompletedProcess([], 128, "", "fatal: not a git repo")
        with mock.patch("subprocess.run", return_value=fake):
            assert mod._test_uncommitted_changes() is True

    def test_exclude_path_none_is_backward_compatible(self) -> None:
        assert self._run(" M foo.py", exclude_path=None) is True
