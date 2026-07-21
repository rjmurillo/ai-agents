"""Tests for the git-layer branch context gate."""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.hooks import check_branch_context as gate

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_COMMIT = _REPO_ROOT / ".githooks" / "pre-commit"
_PRE_PUSH = _REPO_ROOT / ".githooks" / "pre-push"


def _write_session(repo_root: Path, data: object) -> Path:
    sessions_dir = repo_root / ".agents" / "sessions"
    sessions_dir.mkdir(parents=True)
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    session_log = sessions_dir / f"{today}-session-1.json"
    session_log.write_text(json.dumps(data), encoding="utf-8")
    return session_log


def _git_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


def test_allows_matching_branch(tmp_path: Path) -> None:
    _write_session(tmp_path, {"session": {"branch": "feat/matching"}})

    with patch.object(gate, "_current_branch", return_value="feat/matching"):
        assert gate.check_branch_context(tmp_path) == 0


def test_blocks_mismatched_branch_and_names_both(
    tmp_path: Path,
    capsys,
) -> None:
    _write_session(tmp_path, {"session": {"branch": "feat/expected"}})

    with patch.object(gate, "_current_branch", return_value="feat/current"):
        exit_code = gate.check_branch_context(tmp_path)

    assert exit_code == 2
    stderr = capsys.readouterr().err
    assert "feat/current" in stderr
    assert "feat/expected" in stderr


def test_allows_missing_session_log(tmp_path: Path) -> None:
    with patch.object(gate, "_current_branch", return_value="feat/current"):
        assert gate.check_branch_context(tmp_path) == 0


def test_allows_missing_branch_field(tmp_path: Path) -> None:
    _write_session(tmp_path, {"session": {"objective": "test"}})

    with patch.object(gate, "_current_branch", return_value="feat/current"):
        assert gate.check_branch_context(tmp_path) == 0


def test_allows_detached_head(tmp_path: Path) -> None:
    _write_session(tmp_path, {"session": {"branch": "feat/expected"}})

    with patch.object(gate, "_current_branch", return_value=None):
        assert gate.check_branch_context(tmp_path) == 0


def test_reads_legacy_top_level_branch(tmp_path: Path) -> None:
    session_log = _write_session(tmp_path, {"branch": "feat/legacy"})

    assert gate._session_branch(session_log) == "feat/legacy"


def test_invalid_json_fails_open(tmp_path: Path) -> None:
    session_log = _write_session(tmp_path, {})
    session_log.write_text("{", encoding="utf-8")

    assert gate._session_branch(session_log) is None


def test_non_object_json_fails_open(tmp_path: Path) -> None:
    session_log = _write_session(tmp_path, [])

    assert gate._session_branch(session_log) is None


@pytest.mark.parametrize(
    "result",
    [None, _git_result("", returncode=128), _git_result("")],
)
def test_current_branch_fails_open_when_git_has_no_branch(
    tmp_path: Path,
    result: subprocess.CompletedProcess[str] | None,
) -> None:
    with patch.object(gate, "_run_git", return_value=result):
        assert gate._current_branch(tmp_path) is None


def test_session_lookup_uses_newest_readable_log(tmp_path: Path) -> None:
    old_log = _write_session(tmp_path, {"session": {"branch": "feat/old"}})
    new_log = old_log.with_name(old_log.name.replace("session-1", "session-2"))
    new_log.write_text('{"session":{"branch":"feat/new"}}', encoding="utf-8")
    os.utime(old_log, (1, 1))
    os.utime(new_log, (2, 2))

    assert gate._today_session_log(tmp_path) == new_log


def test_session_lookup_skips_log_when_stat_fails(tmp_path: Path) -> None:
    unreadable = _write_session(tmp_path, {"session": {"branch": "feat/bad"}})
    readable = unreadable.with_name(unreadable.name.replace("session-1", "session-2"))
    readable.write_text('{"session":{"branch":"feat/good"}}', encoding="utf-8")
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


def test_main_uses_git_worktree_root(tmp_path: Path) -> None:
    with patch.object(gate, "_run_git", return_value=_git_result(f"{tmp_path}\n")), patch.object(
        gate,
        "check_branch_context",
        return_value=2,
    ) as check:
        assert gate.main() == 2

    check.assert_called_once_with(tmp_path)


def test_main_fails_open_when_repo_root_is_unavailable() -> None:
    with patch.object(gate, "_run_git", return_value=None):
        assert gate.main() == 0


def test_run_git_handles_timeout(tmp_path: Path) -> None:
    with patch.object(
        gate.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired("git", 10),
    ):
        assert gate._run_git(tmp_path, "status") is None


def test_run_git_decodes_with_utf8_replacement(tmp_path: Path) -> None:
    with patch.object(
        gate.subprocess,
        "run",
        return_value=_git_result("feat/café\n"),
    ) as run:
        gate._run_git(tmp_path, "branch", "--show-current")

    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"


def test_script_entry_point_exits_with_main_result(tmp_path: Path) -> None:
    _write_session(tmp_path, {"session": {"branch": "feat/matching"}})
    results = iter(
        [
            _git_result(f"{tmp_path}\n"),
            _git_result("feat/matching\n"),
        ]
    )

    with patch.object(subprocess, "run", side_effect=lambda *args, **kwargs: next(results)):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(gate.__file__, run_name="__main__")

    assert exc_info.value.code == 0


def test_pre_commit_runs_gates_without_lintable_files() -> None:
    text = _PRE_COMMIT.read_text(encoding="utf-8")
    no_files_block = re.search(
        r'if \[ -z "\$STAGED_FILES" \]; then(?P<body>.*?)\nfi',
        text,
        re.DOTALL,
    )

    assert no_files_block is not None
    assert "exit " not in no_files_block.group("body")
    assert "BRANCH_CONTEXT_SCRIPT=" in text
    assert "SESSION_VALIDATE_SCRIPT=" in text
    assert "ADR_REVIEW_SCRIPT=" in text


def test_pre_push_runs_branch_context_before_tree_neutral_exit() -> None:
    text = _PRE_PUSH.read_text(encoding="utf-8")
    branch_context = text.index("BRANCH_CONTEXT_SCRIPT=")
    no_changed_files = text.index('if [ -z "$CHANGED_FILES" ]; then')

    assert branch_context < no_changed_files
    no_changed_block = text[no_changed_files : text.index("\nfi", no_changed_files)]
    assert 'exit "$EXIT_STATUS"' in no_changed_block
