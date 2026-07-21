"""Tests for the git-layer false completion message gate."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.hooks import check_false_completion_msg as gate


def _git_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


def _write_session(repo_root: Path, content: str) -> Path:
    sessions_dir = repo_root / ".agents" / "sessions"
    sessions_dir.mkdir(parents=True)
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    session_log = sessions_dir / f"{today}-session-1.json"
    session_log.write_text(content, encoding="utf-8")
    return session_log


@pytest.mark.parametrize(
    "claim",
    [
        "done with implementation",
        "fixed the bug",
        "completed migration",
        "finished cleanup",
        "resolved issue",
        "merged changes",
        "shipped v2",
        "closes #42",
    ],
)
def test_completion_signals_match_source_contract(claim: str) -> None:
    assert gate.is_completion_claim(claim) is True


@pytest.mark.parametrize(
    "message",
    [
        "feat: add validation",
        "## Completed",
        "Finished:",
        "- Resolved",
        "* Done",
    ],
)
def test_non_claims_and_heading_lines_are_allowed(message: str) -> None:
    assert gate.is_completion_claim(message) is False


def test_prose_below_heading_remains_a_claim() -> None:
    message = "## Completed\n\nfinished the migration"

    assert gate.is_completion_claim(message) is True


@pytest.mark.parametrize(
    ("command", "result"),
    [
        ("uv run pytest", "42 passed"),
        ("npm test", "PASSED"),
        ("tsc --noEmit", "exit code: 0"),
        ("dotnet test", "exited with 0"),
        ("go test", "All checks have passed"),
        ("gh pr checks", "checks passed"),
        ("Invoke-Pester", "✓"),
    ],
)
def test_successful_verification_patterns_match_source_contract(
    tmp_path: Path,
    command: str,
    result: str,
) -> None:
    session_log = _write_session(tmp_path, f"{command}\n{result}\n")

    assert gate._has_verification_evidence(session_log) is True


def test_failing_verification_does_not_satisfy_gate(tmp_path: Path) -> None:
    session_log = _write_session(tmp_path, "uv run pytest\n3 failed\nFAILED\n")

    assert gate._has_verification_evidence(session_log) is False


def test_command_without_success_result_does_not_satisfy_gate(tmp_path: Path) -> None:
    session_log = _write_session(tmp_path, "Need to run pytest\n")

    assert gate._has_verification_evidence(session_log) is False


def test_unreadable_session_log_has_no_evidence(tmp_path: Path) -> None:
    with patch.object(Path, "open", side_effect=OSError("read failed")):
        assert gate._has_verification_evidence(tmp_path / "session.json") is False


def test_completion_claim_with_successful_evidence_is_allowed(tmp_path: Path) -> None:
    _write_session(tmp_path, "uv run pytest\n18 passed\n")

    assert gate.completion_block_reason("fixed everything", tmp_path) is None


def test_completion_claim_without_evidence_is_blocked(tmp_path: Path) -> None:
    _write_session(tmp_path, json.dumps({"work": ["edited code"]}))

    reason = gate.completion_block_reason("fixed everything", tmp_path)

    assert reason is not None
    assert "lacks successful verification" in reason


def test_completion_claim_without_session_log_is_blocked(tmp_path: Path) -> None:
    assert "no session log" in str(
        gate.completion_block_reason("fixed everything", tmp_path)
    )


def test_non_claim_is_allowed_without_session_log(tmp_path: Path) -> None:
    assert gate.completion_block_reason("feat: add parser", tmp_path) is None


def test_environment_bypass_allows_claim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKIP_COMPLETION_GATE", "TrUe")

    assert gate.completion_block_reason("fixed everything", tmp_path) is None


def test_message_file_block_prints_reason(tmp_path: Path, capsys) -> None:
    _write_session(tmp_path, "{}")
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fixed everything\n", encoding="utf-8")

    assert gate.check_message_file(message, tmp_path) == 2
    assert "false completion gate" in capsys.readouterr().err


def test_message_file_allows_verified_claim(tmp_path: Path) -> None:
    _write_session(tmp_path, "pytest\n1 passed\n")
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fixed everything\n", encoding="utf-8")

    assert gate.check_message_file(message, tmp_path) == 0


def test_missing_message_file_fails_open(tmp_path: Path) -> None:
    assert gate.check_message_file(tmp_path / "missing", tmp_path) == 0


def test_session_lookup_uses_newest_readable_log(tmp_path: Path) -> None:
    old_log = _write_session(tmp_path, "old")
    new_log = old_log.with_name(old_log.name.replace("session-1", "session-2"))
    new_log.write_text("new", encoding="utf-8")
    os.utime(old_log, (1, 1))
    os.utime(new_log, (2, 2))

    assert gate._today_session_log(tmp_path) == new_log


def test_session_lookup_skips_log_when_stat_fails(tmp_path: Path) -> None:
    unreadable = _write_session(tmp_path, "bad")
    readable = unreadable.with_name(unreadable.name.replace("session-1", "session-2"))
    readable.write_text("good", encoding="utf-8")
    original_stat = Path.stat

    def fake_stat(path: Path, *args, **kwargs):
        if path == unreadable:
            raise OSError("stat failed")
        return original_stat(path, *args, **kwargs)

    with patch.object(Path, "stat", fake_stat):
        assert gate._today_session_log(tmp_path) == readable


def test_session_lookup_fails_open_when_glob_fails(tmp_path: Path) -> None:
    (tmp_path / ".agents" / "sessions").mkdir(parents=True)

    with patch.object(Path, "glob", side_effect=OSError("glob failed")):
        assert gate._today_session_log(tmp_path) is None


def test_run_git_handles_timeout() -> None:
    with patch.object(
        gate.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired("git", 5),
    ):
        assert gate._run_git("status") is None


def test_run_git_decodes_with_utf8_replacement() -> None:
    with patch.object(
        gate.subprocess,
        "run",
        return_value=_git_result("café\n"),
    ) as run:
        gate._run_git("status")

    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"


@pytest.mark.parametrize(
    "result",
    [None, _git_result("", returncode=1), _git_result("")],
)
def test_repo_root_fails_open_when_git_has_no_root(
    result: subprocess.CompletedProcess[str] | None,
) -> None:
    with patch.object(gate, "_run_git", return_value=result):
        assert gate._repo_root() is None


def test_main_checks_message_file_in_worktree(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fixed everything", encoding="utf-8")

    with patch.object(gate, "_run_git", return_value=_git_result(f"{tmp_path}\n")), patch.object(
        gate,
        "check_message_file",
        return_value=2,
    ) as check:
        assert gate.main([str(message)]) == 2

    check.assert_called_once_with(message, tmp_path)


def test_main_fails_open_without_exactly_one_message_path() -> None:
    assert gate.main([]) == 0
    assert gate.main(["one", "two"]) == 0


def test_main_fails_open_when_repo_root_is_unavailable(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fixed everything", encoding="utf-8")

    with patch.object(gate, "_run_git", return_value=None):
        assert gate.main([str(message)]) == 0


def test_script_entry_point_exits_with_main_result(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: add parser", encoding="utf-8")

    with patch.object(sys, "argv", [gate.__file__, str(message)]), patch.object(
        subprocess,
        "run",
        return_value=_git_result(f"{tmp_path}\n"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(gate.__file__, run_name="__main__")

    assert exc_info.value.code == 0
