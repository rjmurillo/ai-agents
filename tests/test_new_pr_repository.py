"""Repository and audit helper tests for ``new_pr.py``."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tests.new_pr_test_support import (
    _completed,
    _mod,
    _resolve_validation_base,
    get_repo_root,
    write_audit_log,
)


class TestGetRepoRoot:
    def test_not_in_git_repo_exits_2(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=128, stderr="not a git repository"),
        ):
            with pytest.raises(SystemExit) as exc:
                get_repo_root()
            assert exc.value.code == 2

    def test_returns_repo_root(self):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="/home/user/repo\n", rc=0),
        ):
            assert get_repo_root() == "/home/user/repo"

    def test_uses_show_toplevel(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout="/home/user/repo\n", rc=0)
            get_repo_root()
            assert mock_run.call_args.args[0] == [
                "git",
                "rev-parse",
                "--show-toplevel",
            ]

    def test_git_env_strips_hook_overrides(self, monkeypatch):
        monkeypatch.setenv("GIT_DIR", "/wrong/git")
        monkeypatch.setenv("GIT_WORK_TREE", "/wrong/worktree")
        monkeypatch.setenv("GIT_COMMON_DIR", "/wrong/common")
        monkeypatch.setenv("GIT_INDEX_FILE", "/wrong/index")
        env = _mod._git_env()
        assert "GIT_DIR" not in env
        assert "GIT_WORK_TREE" not in env
        assert "GIT_COMMON_DIR" not in env
        assert "GIT_INDEX_FILE" not in env

    def test_returns_worktree_top_not_main_checkout(self):
        """In a linked worktree, repo root is the worktree top (#2387)."""
        worktree_top = "/repo/.git/worktrees/feat/checkout"
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=worktree_top + "\n", rc=0),
        ):
            assert get_repo_root() == worktree_top


class TestWriteAuditLog:
    def test_creates_audit_file(self, tmp_path):
        write_audit_log(str(tmp_path), "feat/branch", "main", "feat: test", "hotfix")
        audit_dir = tmp_path / ".agents" / "audit"
        assert audit_dir.exists()
        files = list(audit_dir.glob("pr-creation-skip-*.txt"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "feat/branch" in content
        assert "hotfix" in content
        assert "SKIPPED" in content

    def test_uses_username_env(self, tmp_path):
        with patch.dict(os.environ, {"USERNAME": "testuser"}, clear=False):
            write_audit_log(str(tmp_path), "feat/b", "main", "feat: t", "reason")
        files = list((tmp_path / ".agents" / "audit").glob("*.txt"))
        content = files[0].read_text()
        assert "testuser" in content

    def test_falls_back_to_user_env(self, tmp_path):
        env = {key: value for key, value in os.environ.items() if key != "USERNAME"}
        env["USER"] = "fallbackuser"
        with patch.dict(os.environ, env, clear=True):
            write_audit_log(str(tmp_path), "feat/b", "main", "feat: t", "reason")
        files = list((tmp_path / ".agents" / "audit").glob("*.txt"))
        content = files[0].read_text()
        assert "fallbackuser" in content


class TestResolveValidationBase:
    """Select the right git ref for local validation diffs."""

    def test_returns_explicit_when_provided(self):
        """Explicit --validation-base overrides everything; no git call made."""
        with patch("subprocess.run") as mock_run:
            result = _resolve_validation_base(
                "main",
                explicit="refs/remotes/upstream/main",
            )
        assert result == "refs/remotes/upstream/main"
        mock_run.assert_not_called()

    def test_returns_origin_ref_when_it_exists(self):
        """When origin/main resolves, return origin/main, not main."""
        with patch("subprocess.run", return_value=_completed(rc=0)) as mock_run:
            result = _resolve_validation_base("main")
        assert result == "origin/main"
        mock_run.assert_called_once()
        argv = mock_run.call_args[0][0]
        assert argv == ["git", "rev-parse", "--verify", "origin/main"]

    def test_falls_back_to_pr_base_when_origin_absent(self):
        """When origin/main does not exist (no remote), fall back to main."""
        with patch("subprocess.run", return_value=_completed(rc=1)):
            result = _resolve_validation_base("main")
        assert result == "main"

    def test_non_main_base_resolves_origin_ref(self):
        """Works for any base branch name, not just main."""
        with patch("subprocess.run", return_value=_completed(rc=0)):
            result = _resolve_validation_base("develop")
        assert result == "origin/develop"

    def test_explicit_empty_string_triggers_auto_resolve(self):
        """Empty explicit value is absent, so auto-resolution runs."""
        with patch("subprocess.run", return_value=_completed(rc=0)):
            result = _resolve_validation_base("main", explicit="")
        assert result == "origin/main"
