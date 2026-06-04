#!/usr/bin/env python3
"""Tests for session-init skill Python modules and scripts."""

from __future__ import annotations

import json
import os
import subprocess
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Module: common_types
# ---------------------------------------------------------------------------


def test_application_failed_error_is_exception():
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from session_init.common_types import ApplicationFailedError

    assert issubclass(ApplicationFailedError, Exception)
    err = ApplicationFailedError("test msg")
    assert str(err) == "test msg"


# ---------------------------------------------------------------------------
# Module: git_helpers
# ---------------------------------------------------------------------------


class TestGitHelpers:
    @pytest.fixture(autouse=True)
    def _setup_path(self):
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    def test_get_git_info_success(self):
        from session_init.git_helpers import get_git_info

        fake_results = {
            ("rev-parse", "--show-toplevel"): "/fake/root",
            ("branch", "--show-current"): "feat/test",
            ("rev-parse", "--short", "HEAD"): "abc1234",
            ("status", "--short"): "",
        }

        def mock_run(cmd, **kwargs):
            git_args = tuple(cmd[1:])
            stdout = fake_results.get(git_args, "")
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            info = get_git_info()

        assert info["repo_root"] == "/fake/root"
        assert info["branch"] == "feat/test"
        assert info["commit"] == "abc1234"
        assert info["status"] == "clean"

    def test_get_git_info_dirty(self):
        from session_init.git_helpers import get_git_info

        fake_results = {
            ("rev-parse", "--show-toplevel"): "/fake/root",
            ("branch", "--show-current"): "main",
            ("rev-parse", "--short", "HEAD"): "def5678",
            ("status", "--short"): " M file.py",
        }

        def mock_run(cmd, **kwargs):
            git_args = tuple(cmd[1:])
            stdout = fake_results.get(git_args, "")
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            info = get_git_info()

        assert info["status"] == "dirty"


# ---------------------------------------------------------------------------
# Module: template_helpers
# ---------------------------------------------------------------------------


class TestTemplateHelpers:
    @pytest.fixture(autouse=True)
    def _setup_path(self):
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    def test_get_descriptive_keywords_basic(self):
        from session_init.template_helpers import get_descriptive_keywords

        result = get_descriptive_keywords("Debug recurring session validation failures")
        assert "debug" in result
        assert "recurring" in result
        assert "session" in result
        assert "validation" in result
        assert "failures" in result

    def test_get_descriptive_keywords_empty(self):
        from session_init.template_helpers import get_descriptive_keywords

        assert get_descriptive_keywords("") == ""
        assert get_descriptive_keywords("   ") == ""

    def test_get_descriptive_keywords_max_five(self):
        from session_init.template_helpers import get_descriptive_keywords

        result = get_descriptive_keywords(
            "implement complex feature requiring multiple file changes across codebase"
        )
        parts = result.split("-")
        assert len(parts) <= 5

    def test_get_descriptive_keywords_filters_stop_words(self):
        from session_init.template_helpers import get_descriptive_keywords

        result = get_descriptive_keywords("fix the broken test for coverage")
        assert "the" not in result.split("-")
        assert "for" not in result.split("-")

    def test_new_populated_session_log_raises_on_missing_placeholders(self):
        from session_init.template_helpers import new_populated_session_log

        with pytest.raises(ValueError, match="Template missing required placeholders"):
            new_populated_session_log(
                template="No placeholders here",
                git_info={"branch": "main", "commit": "abc", "status": "clean"},
                user_input={"session_number": 1, "objective": "test"},
            )

    def test_new_populated_session_log_skip_validation(self):
        from session_init.template_helpers import new_populated_session_log

        tmpl = (
            "Session NN on YYYY-MM-DD branch [branch name] "
            "commit [SHA] obj [What this session aims to accomplish] "
            "status [clean/dirty]"
        )
        result = new_populated_session_log(
            template=tmpl,
            git_info={"branch": "feat/test", "commit": "abc123", "status": "clean"},
            user_input={"session_number": 42, "objective": "Test session"},
            skip_validation=False,
        )
        assert "42" in result
        assert "feat/test" in result
        assert "abc123" in result
        assert "Test session" in result
        assert "clean" in result


# ---------------------------------------------------------------------------
# Script: new_session_log.py
# ---------------------------------------------------------------------------


class TestNewSessionLog:
    def test_main_with_skip_validation(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        script = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "new_session_log.py",
        )

        fake_git = {
            ("rev-parse", "--show-toplevel"): str(tmp_path),
            ("branch", "--show-current"): "feat/test",
            ("rev-parse", "--short", "HEAD"): "abc1234",
            ("status", "--short"): "",
        }

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git":
                git_args = tuple(cmd[1:])
                stdout = fake_git.get(git_args, "")
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        import importlib
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        spec = importlib.util.spec_from_file_location("new_session_log", script)
        mod = importlib.util.module_from_spec(spec)

        with mock.patch("subprocess.run", side_effect=mock_run):
            spec.loader.exec_module(mod)
            result = mod.main([
                "--session-number", "1",
                "--objective", "Test session",
                "--skip-validation",
            ])

        assert result == 0
        json_files = list(sessions_dir.glob("*.json"))
        assert len(json_files) == 1

        data = json.loads(json_files[0].read_text())
        assert data["session"]["number"] == 1
        assert data["session"]["objective"] == "Test session"
        assert data["session"]["branch"] == "feat/test"


# ---------------------------------------------------------------------------
# Script: new_session_log_json.py
# ---------------------------------------------------------------------------


class TestNewSessionLogJson:
    def test_main_creates_json(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        script = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "new_session_log_json.py",
        )

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git":
                git_args = tuple(cmd[1:])
                results = {
                    ("branch", "--show-current"): "feat/json-test",
                    ("rev-parse", "--short", "HEAD"): "def5678",
                    ("rev-parse", "--show-toplevel"): str(tmp_path),
                }
                stdout = results.get(git_args, "")
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        import importlib
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        spec = importlib.util.spec_from_file_location("new_session_log_json", script)
        mod = importlib.util.module_from_spec(spec)

        with mock.patch("subprocess.run", side_effect=mock_run):
            spec.loader.exec_module(mod)
            result = mod.main([
                "--session-number", "5",
                "--objective", "JSON test",
            ])

        assert result == 0
        json_files = list(sessions_dir.glob("*.json"))
        assert len(json_files) == 1

        data = json.loads(json_files[0].read_text())
        assert data["session"]["number"] == 5
        assert data["session"]["objective"] == "JSON test"


# ---------------------------------------------------------------------------
# Regression: #2375 — linked worktree from bare repo
# ---------------------------------------------------------------------------


class TestLinkedWorktreeRepoRoot:
    """Issue #2375: session-init misplaced session logs in linked worktrees.

    `git rev-parse --git-common-dir` points to shared Git storage
    (e.g. /tmp/bare.git) for linked worktrees created from bare repos,
    NOT the worktree checkout root. The fix uses --show-toplevel.
    """

    @pytest.fixture(autouse=True)
    def _setup_path(self):
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    def test_get_git_info_uses_show_toplevel_not_git_common_dir(self):
        """In a linked worktree from a bare repo, --git-common-dir != worktree root."""
        from session_init.git_helpers import get_git_info

        worktree_root = "/tmp/bare/ai-agents-pr-2353"
        bare_common_dir = "/tmp/bare/ai-agents.git"

        fake_results = {
            ("rev-parse", "--show-toplevel"): worktree_root,
            ("rev-parse", "--git-common-dir"): bare_common_dir,
            ("branch", "--show-current"): "feat/agent-catalog-and-checkpoint",
            ("rev-parse", "--short", "HEAD"): "3bdb2aac0d",
            ("status", "--short"): "",
        }

        def mock_run(cmd, **kwargs):
            git_args = tuple(cmd[1:])
            stdout = fake_results.get(git_args, "")
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            info = get_git_info()

        # Repo root must be the worktree checkout, not the parent of the
        # bare common-dir (which would be "/tmp/bare").
        assert info["repo_root"] == worktree_root
        assert info["repo_root"] != "/tmp/bare"

    def test_new_session_log_json_uses_show_toplevel(self, tmp_path):
        """new_session_log_json.py must place sessions under the worktree."""
        import importlib
        import sys
        from pathlib import Path

        worktree_root = str(tmp_path / "ai-agents-pr-2353")
        bare_common_dir = str(tmp_path / "ai-agents.git")
        os.makedirs(worktree_root, exist_ok=True)

        script = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "new_session_log_json.py",
        )

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git":
                git_args = tuple(cmd[1:])
                results = {
                    ("rev-parse", "--show-toplevel"): worktree_root,
                    ("rev-parse", "--git-common-dir"): bare_common_dir,
                    ("branch", "--show-current"): "feat/test",
                    ("rev-parse", "--short", "HEAD"): "deadbee",
                }
                stdout = results.get(git_args, "")
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        spec = importlib.util.spec_from_file_location("new_session_log_json_2375", script)
        mod = importlib.util.module_from_spec(spec)

        with mock.patch("subprocess.run", side_effect=mock_run):
            spec.loader.exec_module(mod)
            result = mod.main([
                "--session-number", "2335",
                "--objective", "Linked worktree regression",
            ])

        assert result == 0
        expected_dir = os.path.join(worktree_root, ".agents", "sessions")
        json_files = list(Path(expected_dir).glob("*.json"))
        assert len(json_files) == 1, f"expected file under {expected_dir}, got nothing"
