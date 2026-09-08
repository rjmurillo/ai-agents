"""Tests for #4462: manage_squash_merge_message.py.

The guarded repository-setting operation for
`squash_merge_commit_message` (read, expected-current guard, no-op,
dry-run, write with before/after reporting).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "repo" / "manage_squash_merge_message.py"
)


def _import_script():
    spec = importlib.util.spec_from_file_location("_manage_squash_mod", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_manage_squash_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script()

_MOCK_REPO = RepoInfo(owner="testowner", repo="testrepo")


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class TestFetchCurrentSetting:
    def test_returns_stripped_stdout_value(self):
        with patch(
            f"{_mod.__name__}.subprocess.run",
            return_value=_completed(stdout="COMMIT_MESSAGES\n"),
        ):
            assert _mod.fetch_current_setting("o", "r") == "COMMIT_MESSAGES"

    def test_blank_stdout_defaults_to_pr_body(self):
        with patch(f"{_mod.__name__}.subprocess.run", return_value=_completed(stdout="")):
            assert _mod.fetch_current_setting("o", "r") == "PR_BODY"

    def test_nonzero_exit_raises_runtime_error(self):
        with (
            patch(
                f"{_mod.__name__}.subprocess.run",
                return_value=_completed(rc=1, stderr="404 Not Found"),
            ),
            pytest.raises(RuntimeError, match="404 Not Found"),
        ):
            _mod.fetch_current_setting("o", "r")

    def test_blank_stderr_falls_back_to_generic_message(self):
        with (
            patch(f"{_mod.__name__}.subprocess.run", return_value=_completed(rc=1, stderr="")),
            pytest.raises(RuntimeError, match="failed with no stderr or stdout"),
        ):
            _mod.fetch_current_setting("o", "r")


class TestUpdateSetting:
    def test_sends_field_via_gh_api(self):
        with patch(
            f"{_mod.__name__}.subprocess.run", return_value=_completed(),
        ) as mock_run:
            _mod.update_setting("o", "r", "PR_BODY")

        command = mock_run.call_args.args[0]
        assert "--field" in command
        assert command[command.index("--field") + 1] == "squash_merge_commit_message=PR_BODY"

    def test_nonzero_exit_raises_runtime_error(self):
        with (
            patch(
                f"{_mod.__name__}.subprocess.run",
                return_value=_completed(rc=1, stderr="422 Unprocessable"),
            ),
            pytest.raises(RuntimeError, match="422 Unprocessable"),
        ):
            _mod.update_setting("o", "r", "PR_BODY")


class TestMainReadOnly:
    def test_no_set_reports_current_value_read_only(self, capsys):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting", return_value="PR_BODY"),
            patch(f"{_mod.__name__}.update_setting") as mock_update,
        ):
            rc = _mod.main(["--output-format", "json"])

        output = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert output["Data"]["action"] == "read"
        assert output["Data"]["before"] == "PR_BODY"
        assert output["Data"]["after"] == "PR_BODY"
        mock_update.assert_not_called()


class TestMainExpectedCurrentGuard:
    def test_mismatch_aborts_with_exit_1(self, capsys):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting", return_value="COMMIT_MESSAGES"),
        ):
            rc = _mod.main([
                "--set", "PR_BODY",
                "--expected-current", "PR_BODY",
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert output["Success"] is False
        assert output["Error"]["Type"] == "VerificationFailed"
        assert output["Error"]["Code"] == 1

    def test_match_proceeds_to_write(self):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting",
                  side_effect=["COMMIT_MESSAGES", "PR_BODY"]),
            patch(f"{_mod.__name__}.update_setting") as mock_update,
            patch(f"{_mod.__name__}.write_skill_output"),
        ):
            rc = _mod.main([
                "--set", "PR_BODY",
                "--expected-current", "COMMIT_MESSAGES",
            ])
        assert rc == 0
        mock_update.assert_called_once_with("testowner", "testrepo", "PR_BODY")


class TestMainNoOpAndDryRun:
    def test_set_equal_to_current_is_a_no_op(self):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting", return_value="PR_BODY"),
            patch(f"{_mod.__name__}.update_setting") as mock_update,
            patch(f"{_mod.__name__}.write_skill_output") as output,
        ):
            rc = _mod.main(["--set", "PR_BODY"])
        assert rc == 0
        mock_update.assert_not_called()
        assert output.call_args.args[0]["action"] == "no-op"

    def test_dry_run_does_not_write(self):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting", return_value="COMMIT_MESSAGES"),
            patch(f"{_mod.__name__}.update_setting") as mock_update,
            patch(f"{_mod.__name__}.write_skill_output") as output,
        ):
            rc = _mod.main(["--set", "PR_BODY", "--dry-run"])
        assert rc == 0
        mock_update.assert_not_called()
        assert output.call_args.args[0]["action"] == "dry-run"
        assert output.call_args.args[0]["would_set"] == "PR_BODY"


class TestMainWriteReportsBeforeAfter:
    def test_successful_write_reports_before_and_after(self):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting",
                  side_effect=["COMMIT_MESSAGES", "PR_BODY"]),
            patch(f"{_mod.__name__}.update_setting"),
            patch(f"{_mod.__name__}.write_skill_output") as output,
        ):
            rc = _mod.main(["--set", "PR_BODY"])
        assert rc == 0
        data = output.call_args.args[0]
        assert data["action"] == "updated"
        assert data["before"] == "COMMIT_MESSAGES"
        assert data["after"] == "PR_BODY"

    def test_after_read_reflects_reality_not_the_request(self):
        """The reported `after` comes from a real re-read, not from
        assuming the write took effect as requested; if GitHub silently
        left the value unchanged, the report must say so rather than lying.
        """
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting",
                  side_effect=["COMMIT_MESSAGES", "COMMIT_MESSAGES"]),
            patch(f"{_mod.__name__}.update_setting"),
            patch(f"{_mod.__name__}.write_skill_output") as output,
        ):
            rc = _mod.main(["--set", "PR_BODY"])
        assert rc == 0
        assert output.call_args.args[0]["after"] == "COMMIT_MESSAGES"

    def test_write_failure_returns_api_error(self, capsys):
        with (
            patch(f"{_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_mod.__name__}.fetch_current_setting", return_value="COMMIT_MESSAGES"),
            patch(f"{_mod.__name__}.update_setting",
                  side_effect=RuntimeError("422 Unprocessable")),
        ):
            rc = _mod.main(["--set", "PR_BODY", "--output-format", "json"])
        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Type"] == "ApiError"


class TestBuildParserRejectsUnknownValues:
    def test_unknown_set_value_is_rejected_by_argparse(self):
        with pytest.raises(SystemExit):
            _mod.build_parser().parse_args(["--set", "NOT_A_REAL_VALUE"])
