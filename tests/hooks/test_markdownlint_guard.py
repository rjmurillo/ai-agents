"""Tests for invoke_markdownlint_guard (pure-Python stdlib verifier).

The markdownlint push guard validates .md files using a shipped pure-Python
stdlib-only linter.  Tests verify:
- Clean .md files pass (returncode 0)
- Invalid .md files are blocked (returncode 1 from verifier -> guard blocks)
- No .md changes are allowed (nothing to validate)
- Verifier invoked with -I -S (isolated, no site) and scrubbed env
- Guard runs in consumer repos (project_only=False)
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
)

import invoke_markdownlint_guard as guard


def _stdin(command: str) -> str:
    import json

    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout=stdout, stderr=""
    )


def _fail(
    returncode: int, stdout: str = "", stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["cmd"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


@pytest.fixture()
def push_command(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin("git push")))


def _make_dispatcher(diff_out, lint_handler):
    def dispatch(args, **kwargs):
        if args and (args[0] == "git" or args[0].endswith("/git")):
            return _ok(diff_out)
        return lint_handler(args, **kwargs)

    return dispatch


def _run(diff_out, lint_handler, tmp_path):
    dispatcher = _make_dispatcher(diff_out, lint_handler)
    with (
        patch("push_guard_base.subprocess.run", side_effect=dispatcher),
        patch("push_guard_base._TRUSTED_GIT", "git"),
        patch("push_guard_base._validate_strict_push_configuration"),
        patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path),
        ),
        patch(
            "invoke_markdownlint_guard.get_project_directory",
            return_value=str(tmp_path),
        ),
    ):
        return guard.main()


class TestCleanMarkdown:
    """Clean .md files pass validation."""

    def test_clean_md_passes(self, push_command, tmp_path):
        def lint(args, **_kw):
            return _ok()

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 0

    def test_no_md_files_passes(self, push_command, tmp_path):
        def lint(args, **_kw):
            raise AssertionError("validator should not run")

        rc = _run("src/app.py\n", lint, tmp_path)
        assert rc == 0


class TestInvalidMarkdown:
    """Invalid .md files are blocked."""

    def test_violations_blocked(self, push_command, tmp_path, capsys):
        def lint(args, **_kw):
            return _fail(
                1,
                stderr="docs/a.md:1: MD041 First line should be a heading",
            )

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2


class TestSecurityFlags:
    """Verifier is invoked with isolation flags and scrubbed env."""

    def test_invoked_with_isolation_flags(self, push_command, tmp_path):
        captured_args: list[list[str]] = []
        captured_env: dict[str, str] | None = None

        def lint(args, **kwargs):
            captured_args.append(list(args))
            nonlocal captured_env
            captured_env = kwargs.get("env")
            return _ok()

        _run("docs/a.md\n", lint, tmp_path)

        verifier_calls = [a for a in captured_args if sys.executable in str(a)]
        assert verifier_calls, "Expected verifier invocation"
        call = verifier_calls[0]
        assert "-I" in call, f"-I flag missing: {call}"
        assert "-S" in call, f"-S flag missing: {call}"

        if captured_env is not None:
            python_vars = [k for k in captured_env if k.startswith("PYTHON")]
            assert not python_vars, f"PYTHON* vars leaked: {python_vars}"

    def test_verifier_missing_blocks(self, push_command, tmp_path, capsys):
        def lint(args, **_kw):
            raise AssertionError("should not reach validator")

        with patch.object(guard.Path, "is_file", return_value=False):
            rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2
        assert "trusted verifier unavailable" in capsys.readouterr().err


class TestConsumerGuardWiring:
    def test_consumer_repo_runs_guard(self, push_command, tmp_path):
        def lint(args, **_kw):
            return _fail(1, stderr="blocked")

        with (
            patch("push_guard_base.skip_if_consumer_repo", return_value=True),
            patch("push_guard_base._TRUSTED_GIT", "git"),
        ):
            rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2

    def test_git_diff_failure_blocks(self, push_command, tmp_path, capsys):
        def dispatch(args, **_kw):
            if args and (args[0] == "git" or args[0].endswith("/git")):
                return _fail(128, stderr="fatal: unavailable")
            raise AssertionError("lint must not run without changeset")

        with (
            patch("push_guard_base.subprocess.run", side_effect=dispatch),
            patch("push_guard_base._TRUSTED_GIT", "git"),
            patch("push_guard_base._validate_strict_push_configuration"),
            patch(
                "push_guard_base.get_project_directory",
                return_value=str(tmp_path),
            ),
            patch("push_guard_base._gh_base_ref", return_value=None),
        ):
            rc = guard.main()
        assert rc == 2
