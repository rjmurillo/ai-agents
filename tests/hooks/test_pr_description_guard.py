"""Tests for invoke_pr_description_guard.

Covers acceptance criteria from issue #1885 (M5 of #1884): clean PR
description passes, CRITICAL mismatch blocks with parsed lines plus the
fix hint, validator config error blocks with the parse-error message,
gh failures fail-open (no PR, missing binary, timeout), validator
TimeoutExpired and OSError fail-open, empty changeset short-circuits in
the framework, and the hooks.json registration includes the guard.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_pr_description_guard as guard  # noqa: E402


def _stdin(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["x"], returncode=0, stdout=stdout, stderr=stderr
    )


def _fail(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["x"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("push_guard_base.skip_if_consumer_repo", return_value=False):
        yield


@pytest.fixture
def push_command(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin("git push origin HEAD")))


def _make_dispatcher(diff_out, gh_handler, validator_handler):
    """Route subprocess.run calls by argv shape.

    All three call sites (push_guard_base git diff, guard gh pr view,
    guard pr_description.py) hit subprocess.run on potentially different
    module globals. Patching both modules with one dispatcher keeps the
    test wiring simple.
    """
    def dispatch(args, **_kw):
        if args and args[0] == "git":
            return _ok(diff_out)
        if args and args[0] == "gh":
            return gh_handler(args)
        # python3 scripts/validation/pr_description.py ...
        return validator_handler(args)
    return dispatch


def _run(diff_out, gh_handler, validator_handler, tmp_path, gh_present=True):
    dispatcher = _make_dispatcher(diff_out, gh_handler, validator_handler)
    which_value = "/usr/bin/gh" if gh_present else None
    with patch(
        "push_guard_base.subprocess.run", side_effect=dispatcher
    ), patch(
        "invoke_pr_description_guard.subprocess.run", side_effect=dispatcher
    ), patch(
        "push_guard_base.get_project_directory", return_value=str(tmp_path)
    ), patch(
        "invoke_pr_description_guard.get_project_directory",
        return_value=str(tmp_path),
    ), patch.object(
        guard.shutil, "which", return_value=which_value
    ):
        return guard.main()


class TestCleanPrDescription:
    def test_clean_returns_zero(self, push_command, tmp_path, capsys):
        def gh(_args):
            return _ok(stdout="1885\n")

        def validator(_args):
            return _ok(stdout="\nPR description matches diff\n")

        rc = _run("docs/a.md\nsrc/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        assert "BLOCKED" not in capsys.readouterr().out


class TestCriticalMismatch:
    def test_critical_blocks_with_violations_and_hint(
        self, push_command, tmp_path, capsys
    ):
        validator_stdout = (
            "Fetching PR #1885 data...\n"
            "PR has 4 changed files\n"
            "Description mentions 3 files\n"
            "\n"
            "Found 2 issue(s):\n"
            "  CRITICAL: 1\n"
            "  WARNING: 1\n"
            "\n"
            "[CRITICAL] File mentioned but not in diff\n"
            "  File: scripts/old_thing.py\n"
            "  Description claims this file was changed, but it's not in "
            "the PR diff\n"
            "\n"
            "[WARNING] Significant file not mentioned\n"
            "  File: src/new_thing.py\n"
            "  This file was changed but not mentioned in the description\n"
            "\n"
            "CRITICAL issues found. Update PR description to match "
            "actual changes.\n"
        )

        def gh(_args):
            return _ok(stdout="1885\n")

        def validator(_args):
            return _fail(1, stdout=validator_stdout)

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 2
        out = capsys.readouterr()
        assert "## BLOCKED [E_PR_DESCRIPTION]" in out.out
        assert "scripts/old_thing.py" in out.out
        assert "File mentioned but not in diff" in out.out
        # Hint is appended
        assert "Update the PR description to mention only files" in out.out
        assert "scripts/validation/pr_description.py --pr-number 1885" in out.out
        # WARNING-only line should not appear as a violation
        assert "[WARNING]" not in out.out


class TestConfigError:
    def test_config_error_blocks_with_parse_message(
        self, push_command, tmp_path, capsys
    ):
        def gh(_args):
            return _ok(stdout="1885\n")

        def validator(_args):
            return _fail(
                2,
                stdout="",
                stderr=(
                    "Error: missing dependency: gh CLI not found. "
                    "Install: https://cli.github.com/\n"
                ),
            )

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 2
        out = capsys.readouterr()
        assert "## BLOCKED [E_PR_DESCRIPTION]" in out.out
        assert "config error" in out.out
        assert "missing dependency" in out.out


class TestNoPrOpen:
    def test_gh_returns_nonzero_fails_open(
        self, push_command, tmp_path, capsys
    ):
        def gh(_args):
            return _fail(
                1,
                stdout="",
                stderr="no pull requests found for branch foo/bar\n",
            )

        def validator(_args):
            raise AssertionError(
                "validator should not run when no PR is open"
            )

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "no PR found for current branch" in err
        assert "fail-open" in err


class TestGhMissing:
    def test_gh_binary_missing_fails_open(
        self, push_command, tmp_path, capsys
    ):
        def gh(_args):
            raise AssertionError(
                "gh subprocess should not be invoked when binary missing"
            )

        def validator(_args):
            raise AssertionError(
                "validator should not run when gh is missing"
            )

        rc = _run(
            "src/foo.py\n", gh, validator, tmp_path, gh_present=False
        )
        assert rc == 0
        err = capsys.readouterr().err
        assert "gh CLI not on PATH" in err
        assert "fail-open" in err


class TestGhTimeout:
    def test_gh_timeout_fails_open(self, push_command, tmp_path, capsys):
        def gh(args):
            raise subprocess.TimeoutExpired(cmd=args, timeout=10)

        def validator(_args):
            raise AssertionError(
                "validator should not run when gh times out"
            )

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "gh pr view timed out" in err
        assert "fail-open" in err


class TestValidatorTimeout:
    def test_validator_timeout_fails_open(
        self, push_command, tmp_path, capsys
    ):
        def gh(_args):
            return _ok(stdout="1885\n")

        def validator(args):
            raise subprocess.TimeoutExpired(cmd=args, timeout=60)

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "pr_description.py timed out" in err
        assert "fail-open" in err


class TestValidatorOSError:
    def test_validator_oserror_fails_open(
        self, push_command, tmp_path, capsys
    ):
        def gh(_args):
            return _ok(stdout="1885\n")

        def validator(_args):
            raise OSError("Exec format error")

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "failed to invoke" in err
        assert "fail-open" in err


class TestGhEdgeCases:
    def test_gh_empty_stdout_fails_open(self, push_command, tmp_path, capsys):
        def gh(_args):
            return _ok(stdout="\n")

        def validator(_args):
            raise AssertionError(
                "validator should not run when PR number is empty"
            )

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "empty PR number" in err
        assert "fail-open" in err

    def test_gh_non_numeric_stdout_fails_open(
        self, push_command, tmp_path, capsys
    ):
        def gh(_args):
            return _ok(stdout="not-a-number\n")

        def validator(_args):
            raise AssertionError(
                "validator should not run when PR number is non-numeric"
            )

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "non-numeric PR number" in err
        assert "fail-open" in err

    def test_gh_oserror_fails_open(self, push_command, tmp_path, capsys):
        def gh(_args):
            raise OSError("Exec format error")

        def validator(_args):
            raise AssertionError(
                "validator should not run on gh OSError"
            )

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "gh pr view failed to invoke" in err
        assert "fail-open" in err


class TestRc1WithoutCriticalLines:
    def test_rc1_without_parseable_critical_lines_emits_generic_violation(
        self, push_command, tmp_path, capsys
    ):
        """rc=1 means CRITICAL per validator contract. If stdout does not
        match the [CRITICAL] block shape (validator change, truncation),
        the guard must still block with a generic message rather than
        silently fail-open.
        """
        def gh(_args):
            return _ok(stdout="1885\n")

        def validator(_args):
            return _fail(1, stdout="something went wrong\n")

        rc = _run("src/foo.py\n", gh, validator, tmp_path)
        assert rc == 2
        out = capsys.readouterr().out
        assert "## BLOCKED [E_PR_DESCRIPTION]" in out
        assert "reported critical issues" in out


class TestEmptyChangeset:
    def test_empty_diff_short_circuits_before_validator(
        self, push_command, tmp_path
    ):
        invoked = {"gh": False, "validator": False}

        def gh(_args):
            invoked["gh"] = True
            return _ok(stdout="1885\n")

        def validator(_args):
            invoked["validator"] = True
            return _ok()

        rc = _run("", gh, validator, tmp_path)
        assert rc == 0
        # Empty changeset means framework short-circuits before glob match,
        # so neither gh nor the validator should run.
        assert invoked["gh"] is False
        assert invoked["validator"] is False


class TestHooksJsonRegistration:
    def test_hooks_json_includes_pr_description_guard(self):
        hooks_path = (
            Path(__file__).resolve().parents[2]
            / ".claude"
            / "hooks"
            / "hooks.json"
        )
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        push_block = next(
            block
            for block in data["hooks"]["PreToolUse"]
            if block.get("matcher") == "Bash(git push*)"
        )
        commands = [hook.get("command", "") for hook in push_block["hooks"]]
        assert any(
            "invoke_pr_description_guard.py" in cmd for cmd in commands
        )

    def test_settings_json_includes_pr_description_guard(self):
        settings_path = (
            Path(__file__).resolve().parents[2] / ".claude" / "settings.json"
        )
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        push_block = next(
            block
            for block in data["hooks"]["PreToolUse"]
            if block.get("matcher") == "Bash(git push*)"
        )
        commands = [hook.get("command", "") for hook in push_block["hooks"]]
        assert any(
            "invoke_pr_description_guard.py" in cmd for cmd in commands
        )
