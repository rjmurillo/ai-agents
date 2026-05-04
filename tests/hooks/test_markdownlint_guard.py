"""Tests for invoke_markdownlint_guard.

Covers acceptance criteria from issue #1884 TASK-005-2: clean files pass,
violations block with structured output, missing binary fails open,
TimeoutExpired and OSError fail open, empty changeset short-circuits in
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

import invoke_markdownlint_guard as guard  # noqa: E402


def _stdin(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["x"], returncode=0, stdout=stdout, stderr=stderr
    )


def _fail(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
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


def _make_dispatcher(diff_out, lint_handler):
    """Single subprocess.run side_effect that routes git diff vs markdownlint.

    Both push_guard_base and invoke_markdownlint_guard call subprocess.run on
    the same module global. Patching with one dispatcher avoids the two-patch
    collision while still letting tests express git-diff and lint behavior
    separately.
    """
    def dispatch(args, **_kw):
        if args and args[0] == "git":
            return _ok(diff_out)
        return lint_handler(args)
    return dispatch


def _run(diff_out, lint_handler, tmp_path, which_value=guard.BINARY):
    dispatcher = _make_dispatcher(diff_out, lint_handler)
    with patch("push_guard_base.subprocess.run", side_effect=dispatcher), \
         patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
         patch.object(guard.shutil, "which", return_value=which_value), \
         patch("invoke_markdownlint_guard.get_project_directory", return_value=str(tmp_path)):
        return guard.main()


class TestCleanFiles:
    def test_clean_returns_zero(self, push_command, tmp_path, capsys):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0\n")
            return _ok()

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 0
        assert "BLOCKED" not in capsys.readouterr().out


class TestViolations:
    def test_violation_blocks_with_structured_output(self, push_command, tmp_path, capsys):
        violation_text = (
            "docs/a.md:5 MD040/fenced-code-language Fenced code blocks "
            "should have a language specified\n"
            "docs/a.md:12 MD013/line-length Line length\n"
        )

        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            return _fail(1, stdout=violation_text)

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2
        out = capsys.readouterr()
        assert "## BLOCKED [E_MARKDOWN_LINT]" in out.out
        assert "MD040/fenced-code-language" in out.out
        assert "MD013/line-length" in out.out
        assert "Fix and re-push." in out.out


class TestBinaryAbsent:
    def test_binary_missing_fails_open(self, push_command, tmp_path, capsys):
        def lint(args):
            raise AssertionError("subprocess should not run when binary missing")

        rc = _run("docs/a.md\n", lint, tmp_path, which_value=None)
        assert rc == 0
        err = capsys.readouterr().err
        assert f"{guard.BINARY} not found on PATH" in err
        assert "fail-open" in err


class TestTimeout:
    def test_timeout_fails_open(self, push_command, tmp_path, capsys):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            raise subprocess.TimeoutExpired(cmd=args, timeout=60)

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "TIMEOUT" in err
        assert "allowing push" in err


class TestOSError:
    def test_oserror_fails_open(self, push_command, tmp_path, capsys):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            raise OSError("Exec format error")

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 0
        err = capsys.readouterr().err
        assert "OSError" in err
        assert "allowing push" in err


class TestEmptyChangeset:
    def test_no_md_files_skips_validator(self, push_command, tmp_path):
        invoked = {"lint": False}

        def lint(args):
            invoked["lint"] = True
            return _ok()

        rc = _run("src/foo.py\nsrc/bar.py\n", lint, tmp_path)
        assert rc == 0
        assert invoked["lint"] is False


class TestHooksJsonRegistration:
    def test_hooks_json_includes_markdownlint_guard(self):
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
        assert any("invoke_markdownlint_guard.py" in cmd for cmd in commands)
