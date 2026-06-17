#!/usr/bin/env python3
"""Tests for session-init skill Python modules and scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
        path = os.path.join(os.path.dirname(__file__), "..")
        if path not in sys.path:
            sys.path.insert(0, path)
            yield
            sys.path.remove(path)
        else:
            yield

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

    def test_get_git_info_uses_worktree_toplevel_not_common_dir(self):
        """In a linked worktree, repo_root is the worktree top, not main checkout.

        Regression for #2375. --git-common-dir returns the MAIN checkout's
        shared .git in a linked worktree; --show-toplevel returns this
        worktree's root. get_git_info must use --show-toplevel.
        """
        from session_init.git_helpers import get_git_info

        worktree_top = "/repo/.git/worktrees/feat/checkout"
        main_common_dir = "/repo/.git"
        fake_results = {
            # If the code regressed to --git-common-dir, repo_root would be
            # dirname(main_common_dir) == "/repo", the main checkout.
            ("rev-parse", "--git-common-dir"): main_common_dir,
            ("rev-parse", "--show-toplevel"): worktree_top,
            ("branch", "--show-current"): "feat/linked",
            ("rev-parse", "--short", "HEAD"): "feed1234",
            ("status", "--short"): "",
        }

        def mock_run(cmd, **kwargs):
            git_args = tuple(cmd[1:])
            stdout = fake_results.get(git_args, "")
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            info = get_git_info()

        assert info["repo_root"] == worktree_top
        assert info["repo_root"] != "/repo"

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
# Module: session_structure (single source of truth, Issue #2591)
# ---------------------------------------------------------------------------


REQUIRED_SESSION_START_KEYS = {
    "serenaActivated",
    "serenaInstructions",
    "handoffRead",
    "sessionLogCreated",
    "skillScriptsListed",
    "usageMandatoryRead",
    "constraintsRead",
    "memoriesLoaded",
    "branchVerified",
    "notOnMain",
    "gitStatusVerified",
    "startingCommitNoted",
}

REQUIRED_SESSION_END_KEYS = {
    "checklistComplete",
    "handoffPreserved",
    "serenaMemoryUpdated",
    "markdownLintRun",
    "changesCommitted",
    "validationPassed",
    "tasksUpdated",
    "retrospectiveInvoked",
}


class TestSessionStructure:
    @pytest.fixture(autouse=True)
    def _setup_path(self):
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    def test_build_session_log_top_level_shape(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="feat/x",
            commit="abc1234",
            session_number=7,
            objective="do the thing",
            current_date="2026-06-17",
        )

        assert set(data.keys()) == {
            "schemaVersion",
            "session",
            "protocolCompliance",
            "workLog",
            "endingCommit",
            "nextSteps",
        }
        assert data["schemaVersion"] == "1.0"
        assert data["session"]["number"] == 7
        assert data["session"]["objective"] == "do the thing"
        assert data["session"]["branch"] == "feat/x"
        assert data["session"]["startingCommit"] == "abc1234"
        assert data["session"]["date"] == "2026-06-17"
        assert data["workLog"] == []
        assert data["endingCommit"] == ""
        assert data["nextSteps"] == []

    def test_build_session_log_protocol_compliance_keys(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="feat/x",
            commit="abc1234",
            session_number=7,
            objective="do the thing",
            current_date="2026-06-17",
        )
        compliance = data["protocolCompliance"]

        assert set(compliance["sessionStart"].keys()) == REQUIRED_SESSION_START_KEYS
        assert set(compliance["sessionEnd"].keys()) == REQUIRED_SESSION_END_KEYS

    def test_build_session_log_not_on_main_for_feature_branch(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="feat/x",
            commit="abc1234",
            session_number=7,
            objective="obj",
            current_date="2026-06-17",
        )
        not_on_main = data["protocolCompliance"]["sessionStart"]["notOnMain"]
        assert not_on_main["Complete"] is True
        assert not_on_main["Evidence"] == "On feat/x"

    def test_build_session_log_not_on_main_false_on_main(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="main",
            commit="abc1234",
            session_number=7,
            objective="obj",
            current_date="2026-06-17",
        )
        assert data["protocolCompliance"]["sessionStart"]["notOnMain"]["Complete"] is False

    def test_build_session_log_default_objective_placeholder(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="feat/x",
            commit="abc1234",
            session_number=7,
            objective="",
            current_date="2026-06-17",
        )
        assert data["session"]["objective"] == "[TODO: Describe objective]"

    def test_build_session_log_optional_trace_metadata(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="feat/x",
            commit="abc1234",
            session_number=7,
            objective="obj",
            current_date="2026-06-17",
            trace_id="trace-123",
            parent_session_id="2026-06-17-session-6",
        )
        assert data["session"]["traceId"] == "trace-123"
        assert data["session"]["parentSessionId"] == "2026-06-17-session-6"

    def test_build_session_log_omits_empty_trace_metadata(self):
        from session_init.session_structure import build_session_log

        data = build_session_log(
            branch="feat/x",
            commit="abc1234",
            session_number=7,
            objective="obj",
            current_date="2026-06-17",
        )
        assert "traceId" not in data["session"]
        assert "parentSessionId" not in data["session"]


class TestGeneratorsShareStructure:
    """Both generators MUST emit the identical session-log schema (Issue #2591).

    Guards against the drift that forced #2537/PR #2588 to fix schemaVersion and
    the trailing newline twice. If either generator stops routing through the
    shared builder, the protocolCompliance blocks diverge and this test fails.
    """

    def _emit(self, tmp_path, script_name, extra_args=None):
        script = os.path.join(
            os.path.dirname(__file__), "..", "scripts", script_name,
        )

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git":
                git_args = tuple(cmd[1:])
                results = {
                    ("branch", "--show-current"): "feat/shared",
                    ("rev-parse", "--short", "HEAD"): "abc1234",
                    ("rev-parse", "--show-toplevel"): str(tmp_path),
                }
                stdout = results.get(git_args, "")
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        import importlib
        scripts_path = os.path.join(os.path.dirname(__file__), "..", "scripts")
        module_name = script_name[: -len(".py")]
        spec = importlib.util.spec_from_file_location(module_name, script)
        mod = importlib.util.module_from_spec(spec)

        argv = ["--session-number", "9", "--objective", "shared obj"]
        if extra_args:
            argv.extend(extra_args)

        with mock.patch("subprocess.run", side_effect=mock_run), pytest.MonkeyPatch.context() as mp:
            mp.syspath_prepend(scripts_path)
            spec.loader.exec_module(mod)
            extra = ["--skip-validation"] if script_name == "new_session_log.py" else []
            result = mod.main([*argv, *extra])

        assert result == 0
        json_files = list((tmp_path / ".agents" / "sessions").glob("*.json"))
        assert len(json_files) == 1
        text = json_files[0].read_text()
        json_files[0].unlink()
        return text, json.loads(text)

    def test_both_generators_emit_identical_protocol_compliance(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        _, primary = self._emit(tmp_path, "new_session_log.py")
        _, simplified = self._emit(tmp_path, "new_session_log_json.py")

        assert primary["protocolCompliance"] == simplified["protocolCompliance"]

    def test_both_generators_share_top_level_keys(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        _, primary = self._emit(tmp_path, "new_session_log.py")
        _, simplified = self._emit(tmp_path, "new_session_log_json.py")

        assert set(primary.keys()) == set(simplified.keys())
        assert primary["schemaVersion"] == simplified["schemaVersion"]

    def test_both_generators_emit_trailing_newline(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        primary_text, _ = self._emit(tmp_path, "new_session_log.py")
        simplified_text, _ = self._emit(tmp_path, "new_session_log_json.py")

        assert primary_text.endswith("\n")
        assert simplified_text.endswith("\n")


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
