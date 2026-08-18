"""Tests for issue #4194: branch-aware session log selection.

Bug: ``check_adr_review_policy`` and ``check_retrospective_evidence`` called
``_today_session_log`` which picks the newest log by mtime. With concurrent
agents on other branches, another agent's newer log would be returned, causing
the gate to judge your commit against the wrong session's evidence.

Fix: ``_session_log_for_current_branch(sessions_dir, repo_root)`` tries
``_session_log_for_branch`` first and falls back to mtime only when no
branch-specific log exists. The ADR and retrospective gates now call this
instead of bare ``_today_session_log``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy


def _init_repo(path: Path, branch: str = "feature/x") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        capture_output=True,
        check=True,
    )


def _write_session_log(
    repo: Path,
    *,
    branch: str,
    name: str = "session-1",
    mtime: float | None = None,
    date: str | None = None,
) -> Path:
    if date is None:
        date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    sessions = repo / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"{date}-{name}.json"
    path.write_text(json.dumps({"session": {"branch": branch}}), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class TestSessionLogForCurrentBranch:
    """_session_log_for_current_branch selects by branch, then falls back to mtime."""

    def test_returns_branch_log_when_branch_matches(self, tmp_path: Path) -> None:
        """Returns the log whose branch field matches, ignoring mtime ordering."""
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        # "other" has a later mtime
        log_other = sessions / f"{today}-session-other.json"
        log_other.write_text(json.dumps({"session": {"branch": "feature/other"}}))
        os.utime(log_other, (2_000_000_000.0, 2_000_000_000.0))
        # "mine" has an earlier mtime but matches the current branch
        log_mine = sessions / f"{today}-session-mine.json"
        log_mine.write_text(json.dumps({"session": {"branch": "feature/x"}}))
        os.utime(log_mine, (1_000_000_000.0, 1_000_000_000.0))

        repo = tmp_path / "repo"
        _init_repo(repo, branch="feature/x")

        result = policy._session_log_for_current_branch(sessions, repo)

        assert result == log_mine, (
            f"Expected the branch-matching log {log_mine.name}, got {result}"
        )

    def test_returns_none_when_no_branch_log_exists(self, tmp_path: Path) -> None:
        """Returns None when no log for the current branch exists.

        The previous behaviour was to fall back to the mtime winner; that
        silently picked another session's log. Returning None lets the caller
        fail with a clear message instead (issue #4288).
        """
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log_old = sessions / f"{today}-session-1.json"
        log_old.write_text(json.dumps({"session": {"branch": "feature/other-a"}}))
        os.utime(log_old, (1_000_000_000.0, 1_000_000_000.0))
        log_new = sessions / f"{today}-session-2.json"
        log_new.write_text(json.dumps({"session": {"branch": "feature/other-b"}}))
        os.utime(log_new, (2_000_000_000.0, 2_000_000_000.0))

        repo = tmp_path / "repo"
        _init_repo(repo, branch="feature/no-log")

        result = policy._session_log_for_current_branch(sessions, repo)

        assert result is None, (
            "Unmatched branch must return None, not the mtime winner. "
            "Returning the mtime winner silently picks another session's log."
        )

    def test_returns_none_when_no_logs_at_all(self, tmp_path: Path) -> None:
        """Returns None when the sessions directory is empty."""
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        repo = tmp_path / "repo"
        _init_repo(repo, branch="feature/x")

        result = policy._session_log_for_current_branch(sessions, repo)

        assert result is None

    def test_returns_none_when_sessions_dir_missing(self, tmp_path: Path) -> None:
        """Returns None when the sessions directory does not exist."""
        sessions = tmp_path / "nonexistent"
        repo = tmp_path / "repo"
        _init_repo(repo, branch="feature/x")

        result = policy._session_log_for_current_branch(sessions, repo)

        assert result is None

    def test_returns_none_when_branch_unavailable(self, tmp_path: Path) -> None:
        """Returns None when _current_branch returns None (detached HEAD etc.).

        The previous behaviour was to fall back to mtime; that silently picked
        another session's log. Returning None lets the caller fail with a clear
        message instead of silently operating on the wrong log (issue #4288).
        """
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log = sessions / f"{today}-session-1.json"
        log.write_text(json.dumps({"session": {"branch": "feature/x"}}))

        repo = tmp_path / "repo"
        _init_repo(repo)

        def no_branch(r: Path) -> None:
            return None

        import unittest.mock as mock

        with mock.patch.object(policy, "_current_branch", no_branch):
            result = policy._session_log_for_current_branch(sessions, repo)

        assert result is None, (
            "Detached HEAD must return None, not the mtime winner. "
            "Returning the mtime winner silently picks another session's log."
        )


class TestRetrospectivePolicyUsesBranchLog:
    """check_retrospective_evidence judges evidence against the current branch's log."""

    def test_gate_calls_session_log_for_current_branch_not_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check_retrospective_evidence calls _session_log_for_current_branch."""
        called_today: list[object] = []
        called_branch: list[object] = []

        def _fake_today(sessions_dir: object) -> None:
            called_today.append(sessions_dir)

        def _fake_branch(sessions_dir: object, root: object) -> None:
            called_branch.append(sessions_dir)

        monkeypatch.setattr(policy, "_today_session_log", _fake_today)
        monkeypatch.setattr(policy, "_session_log_for_current_branch", _fake_branch)
        monkeypatch.setattr(policy, "_documentation_only", lambda paths: False)
        monkeypatch.setattr(policy, "_today_retrospective_exists", lambda root: False)

        policy.check_retrospective_evidence(["README.md"], tmp_path)

        assert called_branch, (
            "check_retrospective_evidence must call _session_log_for_current_branch"
        )
        assert not called_today, (
            "check_retrospective_evidence must NOT call _today_session_log directly"
        )

    def test_passes_when_branch_log_has_retrospective(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate passes when branch log has retrospective evidence."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)

        branch_log = sessions / f"{today}-session-mine.json"
        branch_log.write_text(
            json.dumps(
                {
                    "session": {"branch": "feature/retro"},
                    "retrospective": {"completed": True, "summary": "done"},
                }
            )
        )
        os.utime(branch_log, (1_000_000_000.0, 1_000_000_000.0))

        # Newer log for another branch with no retrospective
        other_log = sessions / f"{today}-session-other.json"
        other_log.write_text(json.dumps({"session": {"branch": "feature/other"}}))
        os.utime(other_log, (2_000_000_000.0, 2_000_000_000.0))

        monkeypatch.setattr(
            policy,
            "_session_log_for_current_branch",
            lambda sessions_dir, root: branch_log,
        )
        monkeypatch.setattr(
            policy,
            "_session_has_retrospective_evidence",
            lambda log: log == branch_log,
        )
        monkeypatch.setattr(policy, "_documentation_only", lambda paths: False)
        monkeypatch.setattr(policy, "_today_retrospective_exists", lambda root: False)
        monkeypatch.setattr(policy, "_is_trivial_retrospective_session", lambda log, paths: False)

        result = policy.check_retrospective_evidence(["README.md"], tmp_path)

        assert result == 0, "Should pass when branch log has retrospective evidence"
