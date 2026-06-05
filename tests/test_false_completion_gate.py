#!/usr/bin/env python3
"""Tests for PreToolUse/invoke_false_completion_gate.py.

Covers:
- Completion signal regex detection
- Verification evidence checking in session logs
- Deny output format
- Bypass conditions (env var, docs-only, no session log)
- Consumer repo skip
- Non-commit commands pass through
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PreToolUse"))

import invoke_false_completion_gate  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_worktree_cache():
    """Clear the per-process worktree-root cache between tests.

    ``_resolve_worktree_root`` memoizes its result; without a reset one test's
    resolved root would leak into the next and make assertions order-dependent.
    """
    invoke_false_completion_gate._worktree_root_cache.clear()
    yield
    invoke_false_completion_gate._worktree_root_cache.clear()


class TestCompletionSignalDetection:
    """Test _is_completion_claim regex matching."""

    @pytest.mark.parametrize(
        "command",
        [
            'git commit -m "feat: done with implementation"',
            'git commit -m "fix: fixed the bug"',
            'git commit -m "feat: completed migration"',
            'git commit -m "chore: finished cleanup"',
            'git commit -m "feat: resolved issue"',
            'git commit -m "feat: merged changes"',
            'git commit -m "feat: shipped v2"',
            'git commit -m "fix: closes #42"',
        ],
    )
    def test_detects_completion_signals(self, command: str) -> None:
        assert invoke_false_completion_gate._is_completion_claim(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            'git commit -m "feat: add new validation logic"',
            'git commit -m "refactor: extract helper method"',
            'git commit -m "test: add unit tests for parser"',
            'git commit -m "docs: update README"',
            'git commit -m "chore: update dependencies"',
        ],
    )
    def test_ignores_non_completion_signals(self, command: str) -> None:
        assert invoke_false_completion_gate._is_completion_claim(command) is False


class TestVerificationEvidence:
    """Test _has_verification_evidence_across_logs checking.

    The gate requires BOTH a command pattern (pytest, npm test) AND a
    successful result pattern (passed count, exit code 0). A failing run
    (FAILED, "N failed") MUST NOT satisfy the gate; failing tests prove the
    run happened but do not prove completion.
    """

    def test_finds_pytest_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({
                "work": [{"task": "ran uv run pytest"}, {"output": "42 passed"}]
            }),
            encoding="utf-8",
        )

        assert invoke_false_completion_gate._has_verification_evidence_across_logs(
            [log]
        ) is True

    def test_no_evidence_without_tests(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({"work": [{"task": "edited some files"}]}),
            encoding="utf-8",
        )

        assert invoke_false_completion_gate._has_verification_evidence_across_logs(
            [log]
        ) is False

    def test_no_evidence_when_log_missing(self, tmp_path: Path) -> None:
        nonexistent_log = tmp_path / "nonexistent-session.json"
        assert invoke_false_completion_gate._has_verification_evidence_across_logs(
            [nonexistent_log]
        ) is False

    def test_failing_pytest_does_not_satisfy_gate(self, tmp_path: Path) -> None:
        """Refs cursor thread PRRT_kwDOQoWRls6EnEK7.

        A pytest run that reports failures (FAILED, "3 failed") matches a
        command pattern but does not satisfy the result-pattern requirement,
        because only successful result patterns count as verification.
        """
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({
                "work": [
                    {"task": "ran uv run pytest"},
                    {"output": "FAILED tests/test_foo.py::test_bar - 3 failed"},
                ]
            }),
            encoding="utf-8",
        )

        assert invoke_false_completion_gate._has_verification_evidence_across_logs(
            [log]
        ) is False

    def test_yesterday_evidence_does_not_satisfy_today_logs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Refs cursor thread PRRT_kwDOQoWRls6EnEK4.

        When today's session log exists (a fresh session started today),
        verification MUST come from today. Stale evidence from yesterday's
        log MUST NOT satisfy today's completion claim. Cross-midnight
        fallback only applies when today has no session log at all.
        """
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        # Today's log lacks verification.
        today_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        today_log = sessions_dir / f"{today_str}-session-001.json"
        today_log.write_text(
            json.dumps({"work": [{"task": "edited"}]}), encoding="utf-8"
        )
        # Yesterday's log has verification.
        yesterday_str = (
            datetime.now(tz=UTC) - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        yesterday_log = sessions_dir / f"{yesterday_str}-session-001.json"
        yesterday_log.write_text(
            json.dumps({
                "work": [{"task": "ran pytest"}, {"output": "5 passed"}]
            }),
            encoding="utf-8",
        )

        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: done with task"'},
        }
        with patch.object(
            invoke_false_completion_gate,
            "skip_if_consumer_repo",
            return_value=False,
        ), patch.object(
            invoke_false_completion_gate,
            "_read_stdin_json",
            return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate,
            "_is_documentation_only",
            return_value=False,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            # Today has logs without evidence: must block, no yesterday fallback.
            assert exc_info.value.code == 2


class TestMain:
    """Test main() function flow."""

    def test_skip_consumer_repo(self) -> None:
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_skip_via_env_var(self) -> None:
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.dict("os.environ", {"SKIP_COMPLETION_GATE": "true"}):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_tty_stdin_exits_zero(self) -> None:
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_non_commit_command_passes(self) -> None:
        hook_input = json.dumps({
            "tool_input": {"command": "ls -la"},
        })
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json",
            return_value=json.loads(hook_input),
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_commit_without_completion_signal_passes(self) -> None:
        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: add new validation"'},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_blocks_completion_without_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(json.dumps({"work": []}), encoding="utf-8")

        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: done with implementation"'},
        }
        # main() reads logs via the plural helper get_today_session_logs and
        # passes the list to _has_verification_evidence_across_logs. Patch
        # both so the fixture (dated 2026-01-01) is treated as today and the
        # evidence check returns False, driving the block branch.
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=False,
        ), patch.object(
            invoke_false_completion_gate, "get_today_session_logs", return_value=[log],
        ), patch.object(
            invoke_false_completion_gate,
            "_has_verification_evidence_across_logs",
            return_value=False,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 2

    def test_allows_completion_with_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({"work": [{"task": "ran pytest"}]}),
            encoding="utf-8",
        )

        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: done with implementation"'},
        }
        # See note on test_blocks_completion_without_evidence for why this
        # patches the plural get_today_session_logs.
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=False,
        ), patch.object(
            invoke_false_completion_gate, "get_today_session_logs", return_value=[log],
        ), patch.object(
            invoke_false_completion_gate,
            "_has_verification_evidence_across_logs",
            return_value=True,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_allows_documentation_only(self, tmp_path: Path) -> None:
        hook_input = {
            "tool_input": {"command": 'git commit -m "docs: done updating README"'},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=True,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0


class TestFailOpen:
    """Test fail-open behavior of the script wrapper on unexpected errors."""

    def test_exception_exits_zero(self) -> None:
        """The ``__main__`` wrapper must catch errors and exit 0.

        The previous version only confirmed ``main()`` raised, not that
        the wrapper was fail-open. A blocking exit (code 2) or unhandled
        raise from the wrapper would have passed silently.
        """
        from tests.hook_test_helpers import run_main_wrapper

        def raising_main() -> None:
            raise RuntimeError("boom")

        code, _stdout, stderr = run_main_wrapper(
            invoke_false_completion_gate, raising_main
        )
        assert code == 0
        assert "boom" in stderr


class TestBodyFileFailClosed:
    """Test fail-closed when body-file paths are unreadable.

    Refs cursor bugbot thread PRRT_kwDOQoWRls6Eef5V (PR #1763).
    When git commit -F <path> or gh pr create --body-file <path>
    points outside the trusted allowlist or to a missing file, the gate
    MUST treat that as a completion claim (block until verified) instead
    of silently skipping evaluation.
    """

    def test_commit_message_file_outside_allowlist_fails_closed(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path.parent / "definitely-outside" / "msg.txt"
        command = f'git commit -F {outside}'
        assert invoke_false_completion_gate._is_completion_claim_in_message_file(
            command
        ) == (True, True)

    def test_commit_message_file_missing_fails_closed(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "does-not-exist.txt"
        command = f'git commit -F {missing}'
        assert invoke_false_completion_gate._is_completion_claim_in_message_file(
            command
        ) == (True, True)

    def test_pr_body_file_outside_allowlist_fails_closed(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path.parent / "definitely-outside" / "body.md"
        command = f'gh pr create --body-file {outside}'
        assert invoke_false_completion_gate._is_completion_claim_in_pr_body_file(
            command
        ) == (True, True)

    def test_pr_body_file_missing_fails_closed(self, tmp_path: Path) -> None:
        missing = tmp_path / "no-body.md"
        command = f'gh pr create --body-file {missing}'
        assert invoke_false_completion_gate._is_completion_claim_in_pr_body_file(
            command
        ) == (True, True)

    def test_no_message_file_returns_false(self) -> None:
        """No -F argument means no body-file claim; do not over-block."""
        assert invoke_false_completion_gate._is_completion_claim_in_message_file(
            'git commit -m "feat: ordinary inline message"'
        ) == (False, False)
        assert invoke_false_completion_gate._is_completion_claim_in_pr_body_file(
            'gh pr create --title "x"'
        ) == (False, False)

    def test_unreadable_body_file_blocks_even_with_no_session_logs(
        self, tmp_path: Path
    ) -> None:
        """Regression for Cursor BugBot PRRT_kwDOQoWRls6EfZri.

        When ``gh pr create --body-file`` points at a file outside the
        trusted allowlist the helper returns the fail-closed claim. The
        gate's caller MUST honor that signal even when there are no
        session logs for today; otherwise the no-session fail-open path
        silently bypasses the fail-closed contract.
        """
        outside = tmp_path.parent / "definitely-outside" / "body.md"
        hook_input = {
            "tool_input": {"command": f"gh pr create --body-file {outside}"},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=False,
        ), patch.object(
            invoke_false_completion_gate, "get_today_session_logs", return_value=[],
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 2

    def test_message_file_absolute_path_inside_worktree_is_read(
        self, tmp_path: Path
    ) -> None:
        """Linked-worktree message files are valid inside the current worktree."""
        main_checkout = tmp_path / "main"
        worktree = tmp_path / "linked"
        main_checkout.mkdir()
        worktree.mkdir()
        message = worktree / "COMMIT_EDITMSG"
        message.write_text("feat: parser\n\nfinished the work\n", encoding="utf-8")

        with patch.object(
            invoke_false_completion_gate,
            "get_project_directory",
            return_value=str(main_checkout),
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(worktree),
        ):
            assert invoke_false_completion_gate._read_commit_message_file(
                str(message)
            ) == "feat: parser\n\nfinished the work\n"

    def test_message_file_relative_path_resolves_from_worktree(
        self, tmp_path: Path
    ) -> None:
        """Relative -F paths bind to the current worktree, not the main checkout."""
        main_checkout = tmp_path / "main"
        worktree = tmp_path / "linked"
        main_checkout.mkdir()
        worktree.mkdir()
        (main_checkout / "COMMIT_EDITMSG").write_text("main checkout", encoding="utf-8")
        (worktree / "COMMIT_EDITMSG").write_text("linked worktree", encoding="utf-8")

        with patch.object(
            invoke_false_completion_gate,
            "get_project_directory",
            return_value=str(main_checkout),
        ), patch.object(
            invoke_false_completion_gate,
            "_resolve_worktree_root",
            return_value=str(worktree),
        ):
            assert (
                invoke_false_completion_gate._read_commit_message_file("COMMIT_EDITMSG")
                == "linked worktree"
            )


class TestAllowedTempRoots:
    """_allowed_temp_roots mirrors canonical _candidate_temp_roots semantics."""

    def test_filters_nonexistent_roots(self, monkeypatch, tmp_path) -> None:
        """Non-existent roots are filtered, matching canonical."""
        bogus = tmp_path / "does-not-exist"
        monkeypatch.setenv("TMPDIR", str(bogus))
        roots = invoke_false_completion_gate._allowed_temp_roots()
        assert all(p.exists() for p in roots)
        assert bogus.resolve() not in roots

    def test_deduplicates_by_resolved_string(
        self, monkeypatch, tmp_path
    ) -> None:
        """When TMPDIR resolves to the same place as gettempdir, no dupes."""
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        monkeypatch.setattr(
            invoke_false_completion_gate.tempfile,
            "gettempdir",
            lambda: str(tmp_path),
        )
        roots = invoke_false_completion_gate._allowed_temp_roots()
        resolved = [str(p) for p in roots]
        assert len(resolved) == len(set(resolved))


class TestDeadlineBudget:
    """Total wall-time budget protects the 5s hook timeout."""

    def test_deadline_exceeded_short_circuits_run_git(
        self, monkeypatch
    ) -> None:
        """When the deadline has passed, _run_git returns None without exec."""
        call_count = {"n": 0}

        def fake_run(*args, **kwargs):
            call_count["n"] += 1
            raise AssertionError("should not be called past deadline")

        monkeypatch.setattr(
            invoke_false_completion_gate.subprocess, "run", fake_run
        )
        expired = invoke_false_completion_gate.time.monotonic() - 1.0
        assert invoke_false_completion_gate._run_git(["status"], expired) is None
        assert call_count["n"] == 0

    def test_resolve_base_branch_falls_through_on_symbolic_ref_timeout(
        self, monkeypatch
    ) -> None:
        """symbolic-ref timeout still tries the default-branch loop."""
        sequence = iter(
            [
                None,
                type(
                    "R",
                    (),
                    {"returncode": 0, "stdout": "origin/main\n", "stderr": ""},
                )(),
            ]
        )

        def fake_run_git(args, deadline=None):
            return next(sequence)

        monkeypatch.setattr(
            invoke_false_completion_gate, "_run_git", fake_run_git
        )
        assert (
            invoke_false_completion_gate._resolve_pr_base_branch(
                deadline=None
            )
            == "origin/main"
        )


class TestHeadingWordsDoNotTrip:
    """Section-heading completion words in a body are not claims (issue #2382).

    A commit body that names a section "## Completed" or "Finished:" must not
    block the commit, but a prose claim ("done with the work") still must.
    """

    @pytest.mark.parametrize(
        "body",
        [
            "## Completed",
            "### Finished",
            "Completed:",
            "Finished:",
            "- Resolved",
            "* Done",
            "Done",
            "feat: add parser\n\n## Completed\n\n## Finished",
            "refactor: extract helper\n\nResolved:\nMerged:",
        ],
    )
    def test_heading_words_are_not_claims(self, body: str) -> None:
        assert invoke_false_completion_gate._is_completion_claim(body) is False

    @pytest.mark.parametrize(
        "body",
        [
            "done with the implementation",
            "feat: fixed the parser bug",
            "completed the migration to v2",
            "## Summary\n\nFinished the cleanup and shipped it",
            "resolved issue in the handler",
            "closes #42",
        ],
    )
    def test_prose_claims_still_detected(self, body: str) -> None:
        assert invoke_false_completion_gate._is_completion_claim(body) is True

    def test_strip_heading_lines_keeps_prose(self) -> None:
        text = "## Completed\nfinished the work here\n### Notes"
        stripped = invoke_false_completion_gate._strip_heading_lines(text)
        assert "finished the work here" in stripped
        assert "## Completed" not in stripped
        assert "### Notes" not in stripped

    def test_body_file_heading_words_do_not_block(self, tmp_path: Path) -> None:
        """A -F body whose only completion words are headings is not a claim."""
        msg = tmp_path / "COMMIT_EDITMSG"
        msg.write_text(
            "refactor: extract helper\n\n## Completed\n\n## Finished\n",
            encoding="utf-8",
        )
        command = f"git commit -F {msg}"
        assert invoke_false_completion_gate._is_completion_claim_in_message_file(
            command
        ) == (False, False)

    def test_body_file_prose_claim_still_blocks(self, tmp_path: Path) -> None:
        """A -F body with a real prose claim is still detected as a claim."""
        msg = tmp_path / "COMMIT_EDITMSG"
        msg.write_text(
            "feat: parser\n\nfinished the migration and shipped it\n",
            encoding="utf-8",
        )
        command = f"git commit -F {msg}"
        assert invoke_false_completion_gate._is_completion_claim_in_message_file(
            command
        ) == (True, False)


class TestWorktreeRootResolution:
    """The gate resolves the CURRENT worktree, not the MAIN checkout (#2382)."""

    def test_uses_show_toplevel_over_project_dir(self, monkeypatch) -> None:
        """git rev-parse --show-toplevel wins over CLAUDE_PROJECT_DIR."""
        worktree = "/work/tree/current"
        main_checkout = "/main/checkout"

        def fake_run(args, **kwargs):
            assert args[:3] == ["git", "rev-parse", "--show-toplevel"]
            return type(
                "R", (), {"returncode": 0, "stdout": worktree + "\n", "stderr": ""}
            )()

        monkeypatch.setattr(
            invoke_false_completion_gate.subprocess, "run", fake_run
        )
        monkeypatch.setattr(
            invoke_false_completion_gate,
            "get_project_directory",
            lambda: main_checkout,
        )
        # Path.resolve() normalizes the value; compare on the basename so the
        # test does not depend on the test runner's filesystem layout.
        resolved = invoke_false_completion_gate._resolve_worktree_root()
        assert resolved.endswith("current")
        assert main_checkout not in resolved

    def test_falls_back_to_project_dir_when_not_a_repo(self, monkeypatch) -> None:
        """Non-zero git exit falls back to get_project_directory."""
        main_checkout = "/main/checkout"

        def fake_run(args, **kwargs):
            return type(
                "R", (), {"returncode": 128, "stdout": "", "stderr": "not a repo"}
            )()

        monkeypatch.setattr(
            invoke_false_completion_gate.subprocess, "run", fake_run
        )
        monkeypatch.setattr(
            invoke_false_completion_gate,
            "get_project_directory",
            lambda: main_checkout,
        )
        assert invoke_false_completion_gate._resolve_worktree_root() == main_checkout

    def test_falls_back_when_git_missing(self, monkeypatch) -> None:
        """OSError (git not installed) falls back to get_project_directory."""
        main_checkout = "/main/checkout"

        def fake_run(args, **kwargs):
            raise OSError("git not found")

        monkeypatch.setattr(
            invoke_false_completion_gate.subprocess, "run", fake_run
        )
        monkeypatch.setattr(
            invoke_false_completion_gate,
            "get_project_directory",
            lambda: main_checkout,
        )
        assert invoke_false_completion_gate._resolve_worktree_root() == main_checkout

    def test_result_is_cached(self, monkeypatch) -> None:
        """The probe runs once per process; the second call uses the cache."""
        calls = {"n": 0}

        def fake_run(args, **kwargs):
            calls["n"] += 1
            return type(
                "R", (), {"returncode": 0, "stdout": "/work/tree\n", "stderr": ""}
            )()

        monkeypatch.setattr(
            invoke_false_completion_gate.subprocess, "run", fake_run
        )
        invoke_false_completion_gate._resolve_worktree_root()
        invoke_false_completion_gate._resolve_worktree_root()
        assert calls["n"] == 1

    def test_run_git_targets_worktree_root(self, monkeypatch) -> None:
        """_run_git binds git -C to the resolved worktree root."""
        worktree = "/work/tree/current"
        captured = {}

        def fake_run(args, **kwargs):
            if args[:3] == ["git", "rev-parse", "--show-toplevel"]:
                return type(
                    "R", (), {"returncode": 0, "stdout": worktree + "\n", "stderr": ""}
                )()
            captured["args"] = args
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(
            invoke_false_completion_gate.subprocess, "run", fake_run
        )
        invoke_false_completion_gate._run_git(["status"])
        # git -C <worktree> status
        assert captured["args"][1] == "-C"
        assert captured["args"][2].endswith("current")
