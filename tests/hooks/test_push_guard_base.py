"""Tests for the shared pre-push guard framework.

Covers the 12 acceptance criteria from issue #1884 TASK-005-1: skip
short-circuits, stdin shapes, git diff fallback, glob filtering
(including the multi-segment R-E case), validator dispatch, the
structured BLOCKED output, fail-open exception handling, and the
hooks.json AC-11 matcher contract.
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

from push_guard_base import (  # noqa: E402
    _filter_by_globs,
    _match_glob,
    run_guard,
)


def _stdin_payload(command: str | None) -> str:
    if command is None:
        return json.dumps({"tool_name": "Bash"})
    return json.dumps({"tool_input": {"command": command}})


def _ok_diff(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout=stdout, stderr=""
    )


def _bad_diff() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=128,
        stdout="",
        stderr="fatal: no upstream",
    )


@pytest.fixture
def push_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin_payload("git push origin HEAD")))


def _no_violations(matching: list[str], all_changed: list[str]) -> list[str]:
    return []


def _always_violates(matching: list[str], all_changed: list[str]) -> list[str]:
    return [f"violation in {p}" for p in matching]


class TestSkipShortCircuit:
    """AC: skip_if_consumer_repo returns True bypasses everything."""

    def test_consumer_repo_skip_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = {"validator": False}

        def validator(_m: list[str], _a: list[str]) -> list[str]:
            called["validator"] = True
            return ["should not run"]

        with patch("push_guard_base.skip_if_consumer_repo", return_value=True):
            rc = run_guard(validator, ["*.md"], "test-guard")
        assert rc == 0
        assert called["validator"] is False


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("push_guard_base.skip_if_consumer_repo", return_value=False):
        yield


class TestStdinShapes:
    """AC: tty, empty, missing tool_input, missing command all return 0."""

    def test_stdin_isatty_returns_zero(self) -> None:
        with patch("push_guard_base.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_empty_stdin_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_no_tool_input_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash"}))
        )
        assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_invalid_json_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
        assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_command_not_string_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = json.dumps({"tool_input": {"command": 123}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert run_guard(_always_violates, ["*.md"], "test") == 0


class TestGlobFiltering:
    """AC: no matching files returns 0 without invoking validator."""

    def test_no_matching_files_skips_validator(
        self, monkeypatch: pytest.MonkeyPatch, push_command: None, tmp_path: Path
    ) -> None:
        called = {"validator": False}

        def validator(_m: list[str], _a: list[str]) -> list[str]:
            called["validator"] = True
            return []

        with patch(
            "push_guard_base.subprocess.run",
            return_value=_ok_diff("src/foo.py\nsrc/bar.py\n"),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(validator, ["*.md"], "test")
        assert rc == 0
        assert called["validator"] is False

    def test_validator_clean_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, push_command: None, tmp_path: Path
    ) -> None:
        with patch(
            "push_guard_base.subprocess.run",
            return_value=_ok_diff("docs/readme.md\n"),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(_no_violations, ["*.md"], "test")
        assert rc == 0


class TestValidatorViolations:
    """AC: violation list yields exit 2 with structured BLOCKED output."""

    def test_violations_block_with_structured_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def validator(matching: list[str], _a: list[str]) -> list[str]:
            return ["bad: line 1", "bad: line 2"]

        with patch(
            "push_guard_base.subprocess.run",
            return_value=_ok_diff("docs/a.md\n"),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(validator, ["*.md"], "markdown-lint")

        assert rc == 2
        out = capsys.readouterr()
        assert "## BLOCKED [E_MARKDOWN_LINT]" in out.out
        assert "markdown-lint" in out.out
        assert "bad: line 1" in out.out
        assert "bad: line 2" in out.out
        assert "Fix and re-push." in out.out
        assert "[E_MARKDOWN_LINT] markdown-lint blocked: 2 violation(s)" in out.err


class TestGitDiffFallback:
    """AC: @{push}..HEAD failure falls back to origin/main...HEAD."""

    def test_push_diff_fails_fallback_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        seen: dict[str, list[str]] = {"args": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            seen["args"].append(args[3])
            if args[3] == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        captured: dict[str, list[str]] = {}

        def validator(matching: list[str], all_changed: list[str]) -> list[str]:
            captured["matching"] = list(matching)
            captured["all"] = list(all_changed)
            return []

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(validator, ["*.md"], "test")

        assert rc == 0
        assert "@{push}..HEAD" in seen["args"]
        assert "origin/main...HEAD" in seen["args"]
        assert captured["matching"] == ["docs/a.md"]
        assert captured["all"] == ["docs/a.md"]

    def test_both_diffs_fail_returns_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch(
            "push_guard_base.subprocess.run", return_value=_bad_diff()
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(_always_violates, ["*.md"], "test")
        assert rc == 0
        assert "fail-open" in capsys.readouterr().err

    def test_both_diffs_empty_returns_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        with patch(
            "push_guard_base.subprocess.run", return_value=_ok_diff("")
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(_always_violates, ["*.md"], "test")
        assert rc == 0


class TestFailOpen:
    """AC: any unhandled exception in body returns 0."""

    def test_validator_exception_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def boom(_m: list[str], _a: list[str]) -> list[str]:
            raise RuntimeError("validator crashed")

        with patch(
            "push_guard_base.subprocess.run",
            return_value=_ok_diff("docs/a.md\n"),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(boom, ["*.md"], "test-guard")

        assert rc == 0
        err = capsys.readouterr().err
        assert "test-guard guard error" in err
        assert "RuntimeError" in err
        assert "validator crashed" in err


class TestHooksJsonContract:
    """AC-11: hooks.json must declare the Bash(git push*) matcher exactly."""

    def test_hooks_json_has_git_push_matcher(self) -> None:
        hooks_path = (
            Path(__file__).resolve().parents[2]
            / ".claude"
            / "hooks"
            / "hooks.json"
        )
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        pre_tool_use = data["hooks"]["PreToolUse"]
        matchers = [block.get("matcher") for block in pre_tool_use]
        assert "Bash(git push*)" in matchers


class TestMatchGlob:
    """AC-12: _match_glob honors single- and multi-segment patterns."""

    def test_single_segment_match(self) -> None:
        assert _match_glob("foo.md", "*.md") is True

    def test_single_segment_no_match(self) -> None:
        assert _match_glob("foo.py", "*.md") is False

    def test_multi_segment_skill_match(self) -> None:
        assert (
            _match_glob(".claude/skills/foo/SKILL.md", ".claude/skills/*/SKILL.md")
            is True
        )

    def test_multi_segment_skill_no_cross_segment(self) -> None:
        # Pre-mortem R-E: pathlib.match would (wrongly) match here.
        assert (
            _match_glob(
                ".claude/skills/foo/bar/SKILL.md", ".claude/skills/*/SKILL.md"
            )
            is False
        )

    def test_templates_agents_match(self) -> None:
        assert _match_glob("templates/agents/x.md", "templates/agents/*.md") is True

    def test_templates_agents_no_subdir(self) -> None:
        assert (
            _match_glob("templates/agents/sub/y.md", "templates/agents/*.md")
            is False
        )

    def test_filter_combines_multiple_globs(self) -> None:
        paths = [
            "docs/a.md",
            "src/foo.py",
            ".claude/skills/x/SKILL.md",
            ".claude/skills/x/y/SKILL.md",
            "templates/agents/x.md",
            "templates/agents/sub/y.md",
        ]
        globs = [".claude/skills/*/SKILL.md", "templates/agents/*.md"]
        matched = _filter_by_globs(paths, globs)
        assert ".claude/skills/x/SKILL.md" in matched
        assert "templates/agents/x.md" in matched
        assert ".claude/skills/x/y/SKILL.md" not in matched
        assert "templates/agents/sub/y.md" not in matched
        assert "src/foo.py" not in matched
        assert "docs/a.md" not in matched
