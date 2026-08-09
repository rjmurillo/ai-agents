"""Tests for the shared pre-push guard framework.

Covers the 12 acceptance criteria from issue #1884 TASK-015-1: skip
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
from typing import Any
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import push_guard_base
from push_guard_base import (
    _filter_by_globs,
    _match_glob,
    run_guard,
)

STRICT_PUSH_CONFIG = push_guard_base._validate_strict_push_configuration


def _stdin_payload(command: str | None) -> str:
    if command is None:
        return json.dumps({"tool_name": "Bash"})
    return json.dumps({"tool_input": {"command": command}})



@pytest.fixture(autouse=True)
def _patch_trusted_git():
    """Tests use bare 'git' in dispatch tables; patch trusted resolution."""
    with patch("push_guard_base._TRUSTED_GIT", "git"):
        yield


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


def _missing_config() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=1, stdout="", stderr=""
    )


def _strict_push_responses() -> dict[
    tuple[str, ...], subprocess.CompletedProcess[str]
]:
    missing = _missing_config()
    return {
        ("git", "branch", "--show-current"): _ok_diff("feature\n"),
        ("git", "config", "--get-all", "push.default"): missing,
        ("git", "config", "--get-all", "branch.feature.pushRemote"): missing,
        ("git", "config", "--get-all", "remote.pushDefault"): missing,
        ("git", "config", "--get-all", "branch.feature.remote"): _ok_diff(
            "origin\n"
        ),
        ("git", "config", "--get-all", "remote.origin.push"): missing,
        (
            "git",
            "config",
            "--bool",
            "--get",
            "remote.origin.mirror",
        ): missing,
        ("git", "config", "--bool", "--get", "push.followTags"): missing,
        ("git", "config", "--get-all", "push.recurseSubmodules"): missing,
        ("git", "config", "--bool", "--get", "submodule.recurse"): missing,
    }


def _git_dispatch(
    responses: dict[tuple[str, ...], subprocess.CompletedProcess[str]],
    calls: list[list[str]] | None = None,
):
    def dispatch(args, **_kwargs):
        if calls is not None:
            calls.append(args)
        response = responses.get(tuple(args))
        if response is None:
            raise AssertionError(f"unexpected git command: {args}")
        return response

    return dispatch


@pytest.fixture
def push_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin_payload("git push")))


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


class TestConsumerExecution:
    """Customer-facing guards must run in repositories that install the plugin."""

    def test_consumer_repo_does_not_skip_when_project_only_is_false(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        with patch("push_guard_base.skip_if_consumer_repo", return_value=True), patch(
            "push_guard_base.subprocess.run",
            return_value=_ok_diff("docs/a.md\n"),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(
                _always_violates,
                ["*.md"],
                "test-guard",
                project_only=False,
            )

        assert rc == 2


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("push_guard_base.skip_if_consumer_repo", return_value=False):
        yield


@pytest.fixture(autouse=True)
def _no_gh_base_ref():
    """Default tests to "no PR open" so the fallback chain exercises @{u}
    and origin/HEAD. Tests that specifically target the gh path opt back
    in by patching ``push_guard_base._gh_base_ref`` with their own value.
    """
    with patch("push_guard_base._gh_base_ref", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _safe_strict_push_configuration():
    with patch("push_guard_base._validate_strict_push_configuration"):
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
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
        assert run_guard(_always_violates, ["*.md"], "test") == 0
        event_lines = [
            line
            for line in capsys.readouterr().err.splitlines()
            if line.startswith("EVENT=")
        ]
        assert len(event_lines) == 1
        event = json.loads(event_lines[0].removeprefix("EVENT="))
        assert event["outcome"] == "fail_open"
        assert event["reason"] == "bad_stdin"

    def test_command_not_string_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = json.dumps({"tool_input": {"command": 123}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_empty_command_string_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string command is falsy and should short-circuit."""
        payload = json.dumps({"tool_input": {"command": ""}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_tool_input_missing_command_key_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tool_input present as dict but no command key."""
        payload = json.dumps({"tool_input": {"other": "value"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert run_guard(_always_violates, ["*.md"], "test") == 0

    def test_json_list_payload_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """JSON top-level is a list, not a dict; must not raise AttributeError."""
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([1, 2, 3])))
        assert run_guard(_always_violates, ["*.md"], "test") == 0
        event_lines = [
            line
            for line in capsys.readouterr().err.splitlines()
            if line.startswith("EVENT=")
        ]
        assert len(event_lines) == 1
        event = json.loads(event_lines[0].removeprefix("EVENT="))
        assert event["outcome"] == "fail_open"
        assert event["reason"] == "bad_stdin"

    def test_non_git_push_command_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Defense in depth: framework is push-specific even if matcher widens."""
        payload = json.dumps({"tool_input": {"command": "git status"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        called = {"validator": False}

        def validator(_m: list[str], _a: list[str]) -> list[str]:
            called["validator"] = True
            return ["should not run"]

        with patch(
            "push_guard_base.subprocess.run", return_value=_ok_diff("docs/a.md\n")
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(validator, ["*.md"], "test")

        assert rc == 0
        assert called["validator"] is False

    def test_git_push_with_leading_whitespace_runs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Leading whitespace in command is tolerated; lstrip handles it."""
        payload = json.dumps({"tool_input": {"command": "   git push origin HEAD"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        called = {"validator": False}

        def validator(_m: list[str], _a: list[str]) -> list[str]:
            called["validator"] = True
            return []

        with patch(
            "push_guard_base.subprocess.run", return_value=_ok_diff("docs/a.md\n")
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(validator, ["*.md"], "test")

        assert rc == 0
        assert called["validator"] is True

    def test_git_push_with_internal_whitespace_runs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Multi-space ``git    push`` must reach the validator.

        The Copilot matcher shim collapses ``\\s+`` to a single space
        before deciding whether ``Bash(git push*)`` fires. If the
        framework's command-shape check insisted on the literal
        ``git push`` substring, a real command like
        ``git    push origin HEAD`` would fire the wrapper and then
        short-circuit to 0, bypassing every guard. PR #1887 review
        thread PRRT_kwDOQoWRls5_r7Mf.
        """
        payload = json.dumps({"tool_input": {"command": "git    push origin HEAD"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        called = {"validator": False}

        def validator(_m: list[str], _a: list[str]) -> list[str]:
            called["validator"] = True
            return []

        with patch(
            "push_guard_base.subprocess.run", return_value=_ok_diff("docs/a.md\n")
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(validator, ["*.md"], "test")

        assert rc == 0
        assert called["validator"] is True

    def test_git_pushd_command_does_not_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``git pushd`` (or ``git push-something`` without whitespace) must
        NOT match. The shape check requires ``git`` and ``push`` to be
        separated by whitespace and not be part of a larger token."""
        payload = json.dumps({"tool_input": {"command": "git pushd"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        called = {"validator": False}

        def validator(_m: list[str], _a: list[str]) -> list[str]:
            called["validator"] = True
            return []

        rc = run_guard(validator, ["*.md"], "test")
        assert rc == 0
        assert called["validator"] is False

    def test_oversized_stdin_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CWE-400: stdin larger than the cap is rejected without OOM."""
        # 2 MiB of valid-looking JSON whitespace prefix; cap is 1 MiB.
        oversize = " " * (1_048_577) + json.dumps(
            {"tool_input": {"command": "git push"}}
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(oversize))
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
        # Machine-parseable event line (Observability gate ask).
        assert "EVENT=" in out.err
        event_line = next(
            line for line in out.err.splitlines() if line.startswith("EVENT=")
        )
        event = json.loads(event_line.removeprefix("EVENT="))
        assert event == {
            "guard": "markdown-lint",
            "code": "E_MARKDOWN_LINT",
            "outcome": "block",
            "violations": 2,
            "matched_files": 1,
            "changed_files": 1,
        }


class TestGitDiffFallback:
    """AC: @{push}..HEAD failure falls back to origin/main...HEAD."""

    def test_push_diff_fails_fallback_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            # No upstream set on this branch: rev-parse @{u} fails, fallback
            # walks to symbolic-ref refs/remotes/origin/HEAD which returns
            # origin/main as the remote default.
            if "rev-parse" in args:
                return _bad_diff()
            if "symbolic-ref" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/main\n", stderr=""
                )
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
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
        assert "@{push}..HEAD" in seen["refs"]
        assert "origin/main...HEAD" in seen["refs"]
        assert captured["matching"] == ["docs/a.md"]
        assert captured["all"] == ["docs/a.md"]

    def test_fallback_uses_detected_default_branch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """Fallback must use origin/HEAD (detected) not hardcoded origin/main.

        For PRs targeting a non-main base (e.g., origin/develop),
        origin/main...HEAD pulls in unrelated history. PR #1887 review
        round 8 mitigation.
        """
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return _bad_diff()
            if "symbolic-ref" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/develop\n", stderr=""
                )
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_no_violations, ["*.md"], "test")

        assert rc == 0
        # Fallback must point at the detected default branch, not origin/main.
        assert "origin/develop...HEAD" in seen["refs"]
        assert "origin/main...HEAD" not in seen["refs"]

    def test_fallback_prefers_upstream_over_origin_head(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """Derivative PRs target a parent feature branch, not the remote default.

        When the user has set ``branch.<name>.merge`` (``git push -u``,
        ``git branch --set-upstream-to``), ``rev-parse @{u}`` returns that
        explicit upstream. The fallback must prefer it over
        ``refs/remotes/origin/HEAD`` so a derivative branch's diff scope
        matches what the user actually intends to push, not all of
        ``origin/main`` history.

        See PR #1887 review thread PRRT_kwDOQoWRls5_rGKQ.
        """
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                # Branch is configured to track the parent feature branch.
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="origin/feat/parent-1880\n",
                    stderr="",
                )
            if "symbolic-ref" in args:
                # symbolic-ref would return origin/main, but we should NOT
                # reach this branch when @{u} succeeds.
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/main\n", stderr=""
                )
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_no_violations, ["*.md"], "test")

        assert rc == 0
        assert "origin/feat/parent-1880...HEAD" in seen["refs"]
        assert "origin/main...HEAD" not in seen["refs"]

    def test_fallback_prefers_pr_base_when_gh_returns_one(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """When gh pr view returns baseRefName, that wins over @{u}/origin/HEAD.

        Once a PR exists, baseRefName is ground truth even when the user
        has not set local upstream tracking. This handles the
        derivative-PR case where the PR is opened against a parent
        feature branch but the developer has not run ``git push -u`` yet.
        See PR #1887 review thread r3189474805.
        """
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            # rev-parse and symbolic-ref would also succeed here, but the
            # gh path takes precedence and should short-circuit them.
            if "rev-parse" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/main\n", stderr=""
                )
            if "symbolic-ref" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/main\n", stderr=""
                )
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ), patch(
            "push_guard_base._gh_base_ref",
            return_value="origin/feat/derivative-base",
        ):
            rc = run_guard(_no_violations, ["*.md"], "test")

        assert rc == 0
        assert "origin/feat/derivative-base...HEAD" in seen["refs"]
        assert "origin/main...HEAD" not in seen["refs"]

    def test_fallback_ignores_unresolved_upstream_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """``rev-parse`` may print ``@{upstream}`` verbatim when none is set.

        Some git versions return rc=0 with the literal token instead of
        failing. Treat that as "no upstream" and walk to the symbolic-ref
        fallback rather than feeding an unresolvable ref to ``git diff``.
        """
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="@{upstream}\n", stderr=""
                )
            if "symbolic-ref" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/main\n", stderr=""
                )
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_no_violations, ["*.md"], "test")

        assert rc == 0
        assert "origin/main...HEAD" in seen["refs"]
        assert all("@{" not in ref for ref in seen["refs"] if ref != "@{push}..HEAD")

    def test_fallback_accepts_branch_name_with_at_sign(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """Git refnames legitimately permit ``@`` in branch names.

        ``origin/release@v2`` is a valid ref; the filter that screens out
        the unresolved ``@{upstream}`` token must target the literal
        ``@{`` sequence, not a bare ``@``. PR #1887 review thread
        PRRT_kwDOQoWRls5_2ZzQ.
        """
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/release@v2\n", stderr=""
                )
            if "symbolic-ref" in args:
                # Should not be reached: rev-parse already returned a real ref.
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="origin/main\n", stderr=""
                )
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_no_violations, ["*.md"], "test")

        assert rc == 0
        assert "origin/release@v2...HEAD" in seen["refs"]
        assert "origin/main...HEAD" not in seen["refs"]

    def test_fallback_falls_back_to_main_when_symbolic_ref_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """If both rev-parse @{u} and origin/HEAD lookup fail, default to origin/main."""
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return _bad_diff()
            if "symbolic-ref" in args:
                return _bad_diff()
            ref = args[-1]
            seen["refs"].append(ref)
            if ref == "@{push}..HEAD":
                return _bad_diff()
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_no_violations, ["*.md"], "test")

        assert rc == 0
        assert "origin/main...HEAD" in seen["refs"]

    def test_primary_empty_does_not_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """Empty primary diff is success, not failure: no fallback (R-D mitigation)."""
        seen: dict[str, list[str]] = {"refs": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            seen["refs"].append(args[-1])
            return _ok_diff("")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_always_violates, ["*.md"], "test")

        assert rc == 0
        assert seen["refs"] == ["@{push}..HEAD"]

    def test_include_deletions_uses_acmrd_filter(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """run_guard(include_deletions=True) requests ACMRD so deletions surface.

        Required for guards (manifest-count, pr-description) that fire on
        any change including deletion-only pushes.
        """
        seen: dict[str, list[str]] = {"args": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return _bad_diff()
            if "symbolic-ref" in args:
                return _ok_diff("origin/main\n")
            seen["args"] = args
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            run_guard(_no_violations, ["*.md"], "test", include_deletions=True)

        assert "--diff-filter=ACMRD" in seen["args"]
        assert "--diff-filter=ACMR" not in seen["args"]

    def test_default_excludes_deletions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """Default (include_deletions=False) keeps the ACMR filter."""
        seen: dict[str, list[str]] = {"args": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return _bad_diff()
            if "symbolic-ref" in args:
                return _ok_diff("origin/main\n")
            seen["args"] = args
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            run_guard(_no_violations, ["*.md"], "test")

        assert "--diff-filter=ACMR" in seen["args"]
        assert "--diff-filter=ACMRD" not in seen["args"]

    def test_diff_filter_includes_renames_excludes_deletions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        """Diff filter is ACMR: renamed files still validate; deletions skip.

        AM alone excluded renames, which would let an agent rename a session
        log or markdown file past the guard without revalidation. ACMR
        keeps deletions excluded (no FileNotFoundError downstream) while
        ensuring renames are surfaced. PR #1887 review round 2.
        """
        seen: dict[str, list[str]] = {"args": []}

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            seen["args"] = args
            return _ok_diff("docs/a.md\n")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            run_guard(_no_violations, ["*.md"], "test")

        assert "--diff-filter=ACMR" in seen["args"]
        assert "--diff-filter=AM" not in seen["args"]

    def test_subprocess_timeout_falls_back_then_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """TimeoutExpired in primary diff falls through to fallback; both timing out fails open."""

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=10)

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_always_violates, ["*.md"], "test-guard")

        assert rc == 0
        assert "fail-open" in capsys.readouterr().err

    def test_subprocess_oserror_falls_back_then_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Missing git binary or OSError on both invocations exits 0 with stderr warning."""

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("git: command not found")

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_always_violates, ["*.md"], "test-guard")

        assert rc == 0
        assert "fail-open" in capsys.readouterr().err

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


class TestFailOpen:
    """AC: any unhandled exception in body returns 0."""

    def test_validator_exception_emits_fail_open_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Validator exception path emits structured EVENT for telemetry.

        Without this, a hostile or buggy validator silently allows every
        push and the only signal is human-prose stderr that no telemetry
        pipeline parses. Gate 6 critical finding from /test round 11.
        """
        def boom(_m: list[str], _a: list[str]) -> list[str]:
            raise RuntimeError("validator crashed in test")

        with patch(
            "push_guard_base.subprocess.run",
            return_value=_ok_diff("docs/a.md\n"),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(boom, ["*.md"], "test-guard")

        assert rc == 0
        err_lines = capsys.readouterr().err.splitlines()
        event_lines = [line for line in err_lines if line.startswith("EVENT=")]
        assert len(event_lines) == 1, f"Expected one EVENT line, got: {event_lines}"
        event = json.loads(event_lines[0].removeprefix("EVENT="))
        assert event["guard"] == "test-guard"
        assert event["code"] == "E_TEST_GUARD"
        assert event["outcome"] == "fail_open"
        assert event["reason"] == "exception"
        assert "RuntimeError" in event["detail"]

    def test_diff_failure_emits_fail_open_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Both git diff refs failing emits a structured fail-open EVENT.

        A repo state where neither @{push}..HEAD nor the detected default
        base resolves should not silently bypass every guard.
        """
        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            return _bad_diff()

        with patch("push_guard_base.subprocess.run", side_effect=fake_run), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ):
            rc = run_guard(_always_violates, ["*.md"], "diff-test")

        assert rc == 0
        err_lines = capsys.readouterr().err.splitlines()
        event_lines = [line for line in err_lines if line.startswith("EVENT=")]
        assert len(event_lines) == 1
        event = json.loads(event_lines[0].removeprefix("EVENT="))
        assert event["outcome"] == "fail_open"
        assert event["reason"] == "diff_failed"
        assert event["guard"] == "diff-test"

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


class TestFailClosed:
    """Strict verifiers block when infrastructure prevents the check."""

    def test_diff_failure_blocks(
        self,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch(
            "push_guard_base.subprocess.run", return_value=_bad_diff()
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(
                _always_violates,
                ["*.md"],
                "test-guard",
                fail_closed=True,
            )

        assert rc == 2
        assert "could not determine changed files" in capsys.readouterr().out

    def test_validator_exception_blocks(
        self,
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
            rc = run_guard(
                boom,
                ["*.md"],
                "test-guard",
                fail_closed=True,
            )

        assert rc == 2
        assert "validator crashed" in capsys.readouterr().out

    def test_malformed_hook_input_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))

        rc = run_guard(
            _always_violates,
            ["*.md"],
            "test-guard",
            fail_closed=True,
        )

        assert rc == 2
        assert "invalid hook input" in capsys.readouterr().out

    def test_empty_stdin_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        rc = run_guard(
            _always_violates,
            ["*.md"],
            "test-guard",
            fail_closed=True,
        )

        assert rc == 2
        assert "stdin empty" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "command",
        [
            "git push origin HEAD",
            "git push origin feature:main",
            "git push --all",
            "git push --mirror",
            "git push --tags",
        ],
    )
    def test_ambiguous_push_scope_blocks_before_git_diff(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        command: str,
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(_stdin_payload(command)))

        with patch("push_guard_base.subprocess.run") as run:
            rc = run_guard(
                _always_violates,
                ["*.md"],
                "test-guard",
                fail_closed=True,
            )

        assert rc == 2
        assert "unsupported arguments" in capsys.readouterr().out
        run.assert_not_called()

    @pytest.mark.parametrize(
        "command",
        [
            "git push --signed=$(git reset --hard HEAD~1)",
            "git push --force-with-lease=`git rev-parse HEAD~1`",
        ],
    )
    def test_shell_expansion_blocks_before_subprocess(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        command: str,
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(_stdin_payload(command)))

        with patch("push_guard_base.subprocess.run") as run:
            rc = run_guard(
                _always_violates,
                ["*.md"],
                "test-guard",
                fail_closed=True,
            )

        assert rc == 2
        assert "shell expansion" in capsys.readouterr().out
        run.assert_not_called()

    @pytest.mark.parametrize(
        ("config_key", "config_value", "expected_fragment"),
        [
            ("push.default", "matching", "matching"),
            (
                "remote.origin.push",
                "refs/heads/*:refs/heads/*",
                "remote.origin.push",
            ),
            ("remote.origin.mirror", "true", "remote.origin.mirror"),
            ("push.followTags", "true", "push.followTags"),
            (
                "push.recurseSubmodules",
                "on-demand",
                "push.recurseSubmodules",
            ),
            ("push.recurseSubmodules", "only", "push.recurseSubmodules"),
            ("submodule.recurse", "true", "submodule.recurse"),
        ],
    )
    def test_unsafe_bare_push_configuration_blocks_before_diff(
        self,
        push_command: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        config_key: str,
        config_value: str,
        expected_fragment: str,
    ) -> None:
        responses = _strict_push_responses()
        bool_keys = {
            "remote.origin.mirror",
            "push.followTags",
            "submodule.recurse",
        }
        command: tuple[str, ...]
        if config_key in bool_keys:
            command = ("git", "config", "--bool", "--get", config_key)
        else:
            command = ("git", "config", "--get-all", config_key)
        responses[command] = _ok_diff(f"{config_value}\n")

        with patch(
            "push_guard_base._validate_strict_push_configuration",
            wraps=STRICT_PUSH_CONFIG,
        ), patch(
            "push_guard_base.subprocess.run",
            side_effect=_git_dispatch(responses),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(
                _always_violates,
                ["*.md"],
                "test-guard",
                fail_closed=True,
            )

        assert rc == 2
        assert expected_fragment in capsys.readouterr().out

    def test_safe_bare_push_configuration_reaches_diff(
        self,
        push_command: None,
        tmp_path: Path,
    ) -> None:
        calls: list[list[str]] = []
        responses = _strict_push_responses()
        responses[
            (
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                "@{push}..HEAD",
            )
        ] = _ok_diff("docs/a.md\n")

        with patch(
            "push_guard_base._validate_strict_push_configuration",
            wraps=STRICT_PUSH_CONFIG,
        ), patch(
            "push_guard_base.subprocess.run",
            side_effect=_git_dispatch(responses, calls),
        ), patch("push_guard_base.get_project_directory", return_value=str(tmp_path)):
            rc = run_guard(
                _no_violations,
                ["*.md"],
                "test-guard",
                fail_closed=True,
            )

        assert rc == 0
        assert any(call[:2] == ["git", "diff"] for call in calls)


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

    def test_settings_json_excludes_git_push_matcher(self) -> None:
        """ADR-084 keeps the customer gate off the internal settings surface."""
        settings_path = (
            Path(__file__).resolve().parents[2] / ".claude" / "settings.json"
        )
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "Bash(git push*)" not in json.dumps(data)


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

    def test_multi_star_pattern_uses_fnmatch_fallback(self) -> None:
        """Patterns with more than one * fall through to fnmatch.

        fnmatch's `*` matches any sequence including `/`, so the result is
        recursive cross-segment. This is the documented behavior of the
        fallback path. Callers needing strict single-segment matching must
        use exactly one `*` (the prefix+suffix path).
        """
        # Two stars: fnmatch matches whatever the shell glob would match.
        assert _match_glob("a/x/b/y.md", "a/*/b/*.md") is True
        # fnmatch does NOT anchor `*` to a path segment, so this also matches.
        assert _match_glob("a/x/y/b/z.md", "a/*/b/*.md") is True

    def test_double_star_basename_only_match(self) -> None:
        """Critical: /**/ with single-segment tail (e.g., .claude/hooks/**/*.py).

        This is what M3 uses in production via GLOBS. Without coverage,
        a bug here silently misses or incorrectly matches files under
        nested hook directories.
        """
        assert (
            _match_glob(".claude/hooks/PreToolUse/foo.py", ".claude/hooks/**/*.py")
            is True
        )

    def test_double_star_basename_deeply_nested_match(self) -> None:
        assert (
            _match_glob(
                ".claude/hooks/PreToolUse/sub/foo.py", ".claude/hooks/**/*.py"
            )
            is True
        )

    def test_double_star_prefix_mismatch_no_match(self) -> None:
        assert (
            _match_glob("other/PreToolUse/foo.py", ".claude/hooks/**/*.py")
            is False
        )

    def test_double_star_extension_mismatch_no_match(self) -> None:
        assert (
            _match_glob(".claude/hooks/PreToolUse/foo.md", ".claude/hooks/**/*.py")
            is False
        )

    def test_double_star_multi_part_tail_match(self) -> None:
        """/**/ with multi-segment tail (e.g., a/**/b/c.py) uses sliding match."""
        assert _match_glob("a/x/y/b/c.py", "a/**/b/c.py") is True

    def test_double_star_multi_part_tail_no_match(self) -> None:
        assert _match_glob("a/x/y/d/c.py", "a/**/b/c.py") is False

    def test_overlap_edge_case_no_match(self) -> None:
        """Prefix+suffix overlap must not yield false positives.

        When a path is shorter than prefix+suffix combined, startswith
        and endswith can both pass against overlapping characters,
        leaving an empty middle slice that trivially passes the '/'
        check. The framework guards against this with a length check.
        """
        # `.claude/skills/SKILL.md` overlap-matches the .claude/skills/*/SKILL.md
        # prefix (.claude/skills/, 15 chars) and suffix (/SKILL.md, 9 chars)
        # against a 23-char path. Without the length guard, the false
        # positive would slip through.
        assert (
            _match_glob(".claude/skills/SKILL.md", ".claude/skills/*/SKILL.md")
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


class TestStdinFailOpenTelemetry:
    """Finding 1 (#2806): anomalous stdin shapes still fail open (rc 0) but now
    emit a structured ``EVENT=...`` fail_open line; legitimate no-ops (tty and
    empty stdin) stay silent."""

    @staticmethod
    def _events(stderr_text: str) -> list[dict[str, Any]]:
        return [
            json.loads(line[len("EVENT="):])
            for line in stderr_text.splitlines()
            if line.startswith("EVENT=")
        ]

    def _run(self, monkeypatch: pytest.MonkeyPatch, payload_text: str) -> int:
        monkeypatch.setattr("sys.stdin", io.StringIO(payload_text))
        result: int = run_guard(_always_violates, ["*.md"], "test-guard")
        return result

    def test_invalid_json_emits_fail_open_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(monkeypatch, "{not json") == 0
        events = self._events(capsys.readouterr().err)
        assert len(events) == 1
        assert events[0]["outcome"] == "fail_open"
        assert events[0]["reason"] == "bad_stdin"
        assert events[0]["guard"] == "test-guard"
        assert events[0]["code"] == "E_TEST_GUARD"

    def test_non_dict_payload_emits_fail_open_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(monkeypatch, json.dumps([1, 2, 3])) == 0
        events = self._events(capsys.readouterr().err)
        assert len(events) == 1
        assert "not a JSON object" in events[0]["detail"]

    def test_missing_tool_input_emits_fail_open_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(monkeypatch, json.dumps({"tool_name": "Bash"})) == 0
        events = self._events(capsys.readouterr().err)
        assert len(events) == 1
        assert "tool_input" in events[0]["detail"]

    def test_command_not_string_emits_fail_open_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(monkeypatch, json.dumps({"tool_input": {"command": 123}})) == 0
        events = self._events(capsys.readouterr().err)
        assert len(events) == 1
        assert "command" in events[0]["detail"]

    def test_oversize_stdin_emits_fail_open_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        big = "x" * (push_guard_base.MAX_STDIN_BYTES + 5)
        assert self._run(monkeypatch, big) == 0
        events = self._events(capsys.readouterr().err)
        assert len(events) == 1
        assert "exceeds" in events[0]["detail"]

    def test_empty_stdin_emits_no_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(monkeypatch, "") == 0
        assert self._events(capsys.readouterr().err) == []

    def test_tty_emits_no_event(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("push_guard_base.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert run_guard(_always_violates, ["*.md"], "test-guard") == 0
        assert self._events(capsys.readouterr().err) == []
