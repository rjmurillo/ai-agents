"""Tests for hook_utilities package.

Migrated from tests/HookUtilities.Tests.ps1 per issue #1053.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.hook_utilities import (
    coerce_to_list,
    format_work_item,
    get_project_directory,
    get_recent_session_log,
    get_today_session_log,
    get_today_session_logs,
    is_git_commit_command,
    is_git_commit_or_push_command,
    is_git_push_command,
    is_pr_create_command,
    is_session_logged_command,
    lock_file,
    unlock_file,
)


class TestGetProjectDirectory:
    def test_returns_claude_project_dir_when_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert get_project_directory() == str(tmp_path)

    def test_returns_cwd_when_no_git_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.warns(UserWarning, match="not found"):
            result = get_project_directory()
        assert result == str(tmp_path)

    def test_finds_git_by_walking_up(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        monkeypatch.chdir(sub_dir)
        result = get_project_directory()
        assert result == str(tmp_path)

    def test_ignores_empty_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "  ")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        result = get_project_directory()
        assert result == str(tmp_path)


class TestIsGitCommitCommand:
    def test_returns_true_for_git_commit(self) -> None:
        assert is_git_commit_command("git commit -m 'test'") is True

    def test_returns_true_for_git_ci(self) -> None:
        assert is_git_commit_command("git ci -m 'test'") is True

    def test_returns_false_for_git_status(self) -> None:
        assert is_git_commit_command("git status") is False

    def test_returns_false_for_empty_string(self) -> None:
        assert is_git_commit_command("") is False

    def test_returns_false_for_none(self) -> None:
        assert is_git_commit_command(None) is False

    def test_returns_true_when_preceded_by_whitespace(self) -> None:
        assert is_git_commit_command("  git commit -m 'test'") is True

    def test_returns_false_for_partial_match(self) -> None:
        assert is_git_commit_command("nogit commit") is False


class TestIsGitPushCommand:
    def test_returns_true_for_git_push(self) -> None:
        assert is_git_push_command("git push") is True

    def test_returns_true_for_git_push_with_remote(self) -> None:
        assert is_git_push_command("git push origin main") is True

    def test_returns_true_for_git_push_with_flags(self) -> None:
        assert is_git_push_command("git push -u origin feat/branch") is True

    def test_returns_false_for_git_status(self) -> None:
        assert is_git_push_command("git status") is False

    def test_returns_false_for_git_commit(self) -> None:
        assert is_git_push_command("git commit -m 'test'") is False

    def test_returns_false_for_empty_string(self) -> None:
        assert is_git_push_command("") is False

    def test_returns_false_for_none(self) -> None:
        assert is_git_push_command(None) is False

    def test_returns_true_when_preceded_by_whitespace(self) -> None:
        assert is_git_push_command("  git push") is True


class TestIsGitCommitOrPushCommand:
    def test_returns_true_for_git_commit(self) -> None:
        assert is_git_commit_or_push_command("git commit -m 'test'") is True

    def test_returns_true_for_git_ci(self) -> None:
        assert is_git_commit_or_push_command("git ci -m 'test'") is True

    def test_returns_true_for_git_push(self) -> None:
        assert is_git_commit_or_push_command("git push") is True

    def test_returns_true_for_git_push_with_args(self) -> None:
        assert is_git_commit_or_push_command("git push origin main") is True

    def test_returns_false_for_git_status(self) -> None:
        assert is_git_commit_or_push_command("git status") is False

    def test_returns_false_for_git_pull(self) -> None:
        assert is_git_commit_or_push_command("git pull") is False

    def test_returns_false_for_empty_string(self) -> None:
        assert is_git_commit_or_push_command("") is False

    def test_returns_false_for_none(self) -> None:
        assert is_git_commit_or_push_command(None) is False


class TestIsPrCreateCommand:
    """M7-T3: gh pr create predicate for multi-matcher session_log_guard."""

    def test_matches_basic_pr_create(self) -> None:
        assert is_pr_create_command("gh pr create") is True

    def test_matches_pr_create_with_flags(self) -> None:
        assert is_pr_create_command('gh pr create --title "x" --body "y"') is True

    def test_matches_when_preceded_by_whitespace(self) -> None:
        assert is_pr_create_command("  gh pr create") is True

    def test_does_not_match_pr_view(self) -> None:
        assert is_pr_create_command("gh pr view 123") is False

    def test_does_not_match_pr_edit(self) -> None:
        assert is_pr_create_command("gh pr edit 123") is False

    def test_does_not_match_substring_within_word(self) -> None:
        assert is_pr_create_command("nogh pr create") is False

    def test_returns_false_for_empty(self) -> None:
        assert is_pr_create_command("") is False

    def test_returns_false_for_none(self) -> None:
        assert is_pr_create_command(None) is False


class TestIsSessionLoggedCommand:
    """M7-T3: aggregate predicate for hooks registered under git commit + pr create."""

    def test_true_for_git_commit(self) -> None:
        assert is_session_logged_command("git commit -m x") is True

    def test_true_for_git_ci(self) -> None:
        assert is_session_logged_command("git ci -m x") is True

    def test_true_for_pr_create(self) -> None:
        assert is_session_logged_command("gh pr create --title x") is True

    def test_false_for_git_status(self) -> None:
        assert is_session_logged_command("git status") is False

    def test_false_for_git_push(self) -> None:
        # push is a different matcher's concern (branch_*_guard)
        assert is_session_logged_command("git push origin main") is False

    def test_false_for_pr_view(self) -> None:
        assert is_session_logged_command("gh pr view 123") is False

    def test_false_for_none(self) -> None:
        assert is_session_logged_command(None) is False


class TestGetTodaySessionLog:
    def test_returns_none_for_nonexistent_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning, match="not found"):
            result = get_today_session_log(str(nonexistent))
        assert result is None

    def test_does_not_throw_for_missing_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning):
            result = get_today_session_log(str(nonexistent))
        assert result is None

    def test_returns_none_when_no_logs_exist(self, tmp_path: Path) -> None:
        result = get_today_session_log(str(tmp_path))
        assert result is None

    def test_returns_most_recent_log(self, tmp_path: Path) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        session1 = tmp_path / f"{today}-session-001.json"
        session2 = tmp_path / f"{today}-session-002.json"
        session1.write_text("{}")
        session2.write_text("{}")

        # Set predictable mtime ordering: session2 is newer
        os.utime(session1, (time.time() - 10, time.time() - 10))
        os.utime(session2, (time.time(), time.time()))

        result = get_today_session_log(str(tmp_path))
        assert result is not None
        assert result.name == f"{today}-session-002.json"

    def test_accepts_explicit_date(self, tmp_path: Path) -> None:
        session = tmp_path / "2025-01-15-session-001.json"
        session.write_text("{}")
        result = get_today_session_log(str(tmp_path), date="2025-01-15")
        assert result is not None
        assert result.name == "2025-01-15-session-001.json"

    def test_returns_none_for_wrong_date(self, tmp_path: Path) -> None:
        session = tmp_path / "2025-01-15-session-001.json"
        session.write_text("{}")
        result = get_today_session_log(str(tmp_path), date="2025-01-16")
        assert result is None

    def test_rejects_traversal_in_date(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid date format"):
            get_today_session_log(str(tmp_path), date="../2025-01-15")

    def test_rejects_non_date_string(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid date format"):
            get_today_session_log(str(tmp_path), date="not-a-date")


class TestGetTodaySessionLogs:
    def test_returns_empty_for_nonexistent_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning, match="not found"):
            result = get_today_session_logs(str(nonexistent))
        assert result == []

    def test_does_not_throw_for_missing_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning):
            result = get_today_session_logs(str(nonexistent))
        assert result == []

    def test_returns_all_today_logs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        yesterday = "2020-01-01"

        (tmp_path / f"{today}-session-001.json").write_text("{}")
        (tmp_path / f"{today}-session-002.json").write_text("{}")
        (tmp_path / f"{yesterday}-session-999.json").write_text("{}")

        result = get_today_session_logs(str(tmp_path))
        assert len(result) == 2
        for p in result:
            assert p.name.startswith(f"{today}-session-")


class TestGetRecentSessionLog:
    """Behavior of get_recent_session_log added by PR #1724."""

    def test_returns_none_for_missing_dir(self, tmp_path: Path) -> None:
        with pytest.warns(UserWarning, match="not found"):
            assert get_recent_session_log(str(tmp_path / "missing")) is None

    def test_returns_today_log_when_present(self, tmp_path: Path) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        f = tmp_path / f"{today}-session-01.json"
        f.write_text("{}")
        result = get_recent_session_log(str(tmp_path))
        assert result is not None and result.name == f.name

    def test_falls_back_to_yesterday_when_no_today(self, tmp_path: Path) -> None:
        """Cross-midnight sessions: prefer today; fall back only when today is empty."""
        yesterday = (datetime.now(tz=UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        f = tmp_path / f"{yesterday}-session-01.json"
        f.write_text("{}")
        result = get_recent_session_log(str(tmp_path))
        assert result is not None and result.name == f.name

    def test_prefers_today_over_yesterday(self, tmp_path: Path) -> None:
        """When both dates exist, today wins regardless of mtime."""
        today_d = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        yesterday = (datetime.now(tz=UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        today_f = tmp_path / f"{today_d}-session-01.json"
        yesterday_f = tmp_path / f"{yesterday}-session-99.json"
        today_f.write_text("{}")
        yesterday_f.write_text("{}")
        # Make yesterday newer by mtime to prove date-priority, not mtime-priority.
        os.utime(yesterday_f, (time.time() + 100, time.time() + 100))
        result = get_recent_session_log(str(tmp_path))
        assert result is not None and result.name == today_f.name

    def test_skips_candidate_with_transient_stat_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A single failing stat must not blind the selector to siblings.

        Race conditions (file deleted between glob and stat, transient
        permission error) on one candidate must not cause the whole
        selection to return None when other candidates are healthy.
        """
        today_d = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        bad = tmp_path / f"{today_d}-session-01.json"
        good = tmp_path / f"{today_d}-session-02.json"
        bad.write_text("{}")
        good.write_text("{}")
        real_stat = Path.stat

        def flaky_stat(self: Path, *args: object, **kwargs: object) -> object:
            if self.name == bad.name:
                raise OSError("transient stat failure")
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", flaky_stat)
        with pytest.warns(UserWarning, match="Skipping unreadable session log"):
            result = get_recent_session_log(str(tmp_path))
        assert result is not None and result.name == good.name


class TestCoerceToList:
    """Behavior of coerce_to_list added by PR #1724."""

    def test_none_returns_empty(self) -> None:
        assert coerce_to_list(None) == []

    def test_list_passes_through(self) -> None:
        assert coerce_to_list(["a", "b"]) == ["a", "b"]

    def test_empty_dict_returns_empty(self) -> None:
        """Empty dict is 'no items', not one item. Prevents the
        is_trivial_session false-negative on schema-conformant logs
        where outcomes is an empty object."""
        assert coerce_to_list({}) == []

    def test_dict_with_tasks_key(self) -> None:
        assert coerce_to_list({"tasks": ["x", "y"]}) == ["x", "y"]

    def test_dict_with_nested_list_value(self) -> None:
        assert coerce_to_list({"foo": ["bar"]}) == ["bar"]

    def test_dict_without_list_wraps_as_single_item(self) -> None:
        d = {"k": "v"}
        assert coerce_to_list(d) == [d]

    def test_string_returns_single_item_list(self) -> None:
        assert coerce_to_list("hello") == ["hello"]

    def test_blank_string_returns_empty(self) -> None:
        assert coerce_to_list("   ") == []

    def test_unsupported_type_returns_empty(self) -> None:
        assert coerce_to_list(42) == []


class TestFormatWorkItem:
    """Behavior of format_work_item added by PR #1724."""

    def test_action_only(self) -> None:
        assert format_work_item({"action": "do thing"}) == "do thing"

    def test_step_action_outcome(self) -> None:
        out = format_work_item({"step": 1, "action": "compile", "outcome": "ok"})
        assert "Step 1:" in out and "compile" in out and "ok" in out

    def test_non_string_action_does_not_raise(self) -> None:
        """str() coercion in formatter prevents TypeError when action is a number/dict."""
        assert "42" in format_work_item({"action": 42})
        nested = format_work_item({"action": {"nested": "value"}})
        assert "nested" in nested

    def test_description_fallback(self) -> None:
        assert format_work_item({"description": "summary"}) == "summary"

    def test_task_fallback(self) -> None:
        assert format_work_item({"task": "label"}) == "label"

    def test_unknown_shape_returns_str_repr(self) -> None:
        d = {"only": "weird"}
        assert format_work_item(d) == str(d)


class TestLockUnlock:
    """Smoke test for lock_file/unlock_file added by PR #1724."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows path covered by msvcrt branch")
    def test_lock_then_unlock_does_not_raise(self, tmp_path: Path) -> None:
        target = tmp_path / "lockable.jsonl"
        with open(target, "ab") as f:
            lock_file(f)
            try:
                f.write(b"entry\n")
            finally:
                unlock_file(f)
        assert target.read_bytes() == b"entry\n"


class TestModuleExports:
    def test_all_functions_importable(self) -> None:
        from scripts.hook_utilities import (
            get_project_directory,
            get_today_session_log,
            get_today_session_logs,
            is_git_commit_command,
            is_git_commit_or_push_command,
            is_git_push_command,
            is_project_repo,
            skip_if_consumer_repo,
        )

        assert callable(get_project_directory)
        assert callable(is_git_commit_command)
        assert callable(is_git_push_command)
        assert callable(is_git_commit_or_push_command)
        assert callable(get_today_session_log)
        assert callable(get_today_session_logs)
        assert callable(is_project_repo)
        assert callable(skip_if_consumer_repo)

    def test_all_exports_listed(self) -> None:
        import scripts.hook_utilities as mod

        expected = {
            "coerce_to_list",
            "format_work_item",
            "get_project_directory",
            "get_recent_session_log",
            "get_today_session_log",
            "get_today_session_logs",
            "is_git_commit_command",
            "is_git_commit_or_push_command",
            "is_git_push_command",
            "is_pr_create_command",
            "is_project_repo",
            "is_session_logged_command",
            "lock_file",
            "skip_if_consumer_repo",
            "unlock_file",
            # ADR-062 LSP-first enforcement lib (facade re-exports)
            "FREE_READS",
            "NAV_REQUIRED",
            "PROVIDERS",
            "SYMBOLS_OVERVIEW",
            "SYMBOL_NAVIGATION",
            "WARN_AT",
            "detect_providers",
            "extract_pattern_and_target",
            "is_code_symbol",
            "is_code_target",
            "is_gated_target",
            "is_git_grep",
            "is_grep_search",
            "normalize_path",
            "read_state",
            "record_nav",
            "record_read",
            "record_warmup",
            "reset_state",
            "state_path",
            "strip_zero_width",
            "write_state",
        }
        assert set(mod.__all__) == expected
