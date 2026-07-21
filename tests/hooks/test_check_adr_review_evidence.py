"""Tests for the git-layer ADR review evidence gate."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.hooks import check_adr_review_evidence as gate


def _git_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


def _write_session(repo_root: Path, content: str) -> Path:
    sessions_dir = repo_root / ".agents" / "sessions"
    sessions_dir.mkdir(parents=True)
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    session_log = sessions_dir / f"{today}-session-1.json"
    session_log.write_text(content, encoding="utf-8")
    return session_log


def _write_debate(repo_root: Path, *, stale: bool = False) -> Path:
    analysis_dir = repo_root / ".agents" / "analysis"
    analysis_dir.mkdir(parents=True)
    debate = analysis_dir / "adr-debate.md"
    debate.write_text("review", encoding="utf-8")
    if stale:
        old = (datetime.now(tz=UTC) - timedelta(days=2)).timestamp()
        os.utime(debate, (old, old))
    return debate


@pytest.mark.parametrize(
    "path",
    [
        "ADR-1.md",
        ".agents/architecture/ADR-042-python.md",
        r".agents\architecture\ADR-042-python.md",
        ".agents/SESSION-PROTOCOL.md",
    ],
)
def test_gated_file_patterns_match_source_contract(path: str) -> None:
    assert gate._is_gated_file(path) is True


@pytest.mark.parametrize(
    "path",
    ["README.md", "notADR-1.md", "SESSION-PROTOCOL.md.bak"],
)
def test_gated_file_patterns_reject_unrelated_paths(path: str) -> None:
    assert gate._is_gated_file(path) is False


def test_allows_when_no_gated_files_are_staged(tmp_path: Path) -> None:
    with patch.object(gate, "_staged_gated_files", return_value=[]):
        assert gate.check_adr_review_evidence(tmp_path) == 0


def test_allows_review_with_same_day_debate(tmp_path: Path) -> None:
    _write_session(tmp_path, json.dumps({"work": ["Ran /adr-review"]}))
    _write_debate(tmp_path)

    with patch.object(
        gate,
        "_staged_gated_files",
        return_value=[".agents/architecture/ADR-042.md"],
    ):
        assert gate.check_adr_review_evidence(tmp_path) == 0


def test_blocks_review_with_stale_debate_from_base_branch(
    tmp_path: Path,
    capsys,
) -> None:
    _write_session(tmp_path, "Ran /adr-review")
    _write_debate(tmp_path, stale=True)

    with patch.object(
        gate,
        "_staged_gated_files",
        return_value=[".agents/architecture/ADR-042.md"],
    ), patch.object(gate, "_modified_on_current_branch", return_value=False):
        exit_code = gate.check_adr_review_evidence(tmp_path)

    assert exit_code == 2
    assert "same-day or current-branch" in capsys.readouterr().err


def test_allows_old_debate_modified_on_current_branch(tmp_path: Path) -> None:
    _write_session(tmp_path, "Used adr-review skill")
    _write_debate(tmp_path, stale=True)

    with patch.object(
        gate,
        "_staged_gated_files",
        return_value=[".agents/SESSION-PROTOCOL.md"],
    ), patch.object(gate, "_modified_on_current_branch", return_value=True):
        assert gate.check_adr_review_evidence(tmp_path) == 0


def test_blocks_when_session_log_is_missing(tmp_path: Path, capsys) -> None:
    with patch.object(
        gate,
        "_staged_gated_files",
        return_value=["ADR-1.md"],
    ):
        assert gate.check_adr_review_evidence(tmp_path) == 2

    assert "today's session log" in capsys.readouterr().err


def test_blocks_when_review_evidence_is_missing(tmp_path: Path, capsys) -> None:
    _write_session(tmp_path, "Edited an ADR")

    with patch.object(
        gate,
        "_staged_gated_files",
        return_value=["ADR-1.md"],
    ):
        assert gate.check_adr_review_evidence(tmp_path) == 2

    assert "lack adr-review evidence" in capsys.readouterr().err


def test_blocks_when_staged_diff_cannot_be_read(tmp_path: Path, capsys) -> None:
    with patch.object(gate, "_staged_gated_files", return_value=None):
        assert gate.check_adr_review_evidence(tmp_path) == 2

    assert "unable to inspect" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    [
        "/adr-review",
        "adr-review skill",
        "ADR Review Protocol",
        "multi-agent consensus completed for ADR",
        "architect reviewed, then planner checked, then qa verified",
    ],
)
def test_review_evidence_patterns_match_source_contract(
    tmp_path: Path,
    content: str,
) -> None:
    session_log = _write_session(tmp_path, content)

    assert gate._has_review_evidence(session_log) is True


def test_unreadable_session_log_has_no_evidence(tmp_path: Path) -> None:
    with patch.object(Path, "read_text", side_effect=OSError("read failed")):
        assert gate._has_review_evidence(tmp_path / "session.json") is False


def test_staged_file_lookup_filters_git_output(tmp_path: Path) -> None:
    result = _git_result("README.md\nADR-1.md\n.agents/SESSION-PROTOCOL.md\n")

    with patch.object(gate, "_run_git", return_value=result) as run_git:
        assert gate._staged_gated_files(tmp_path) == [
            "ADR-1.md",
            ".agents/SESSION-PROTOCOL.md",
        ]

    run_git.assert_called_once_with(tmp_path, "diff", "--cached", "--name-only")


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


@pytest.mark.parametrize("result", [None, _git_result("", returncode=1)])
def test_staged_file_lookup_reports_git_failure(
    tmp_path: Path,
    result: subprocess.CompletedProcess[str] | None,
) -> None:
    with patch.object(gate, "_run_git", return_value=result):
        assert gate._staged_gated_files(tmp_path) is None


def test_old_file_is_not_modified_today(tmp_path: Path) -> None:
    debate = _write_debate(tmp_path, stale=True)

    assert gate._modified_today(debate) is False


def test_modified_today_fails_closed_on_stat_error(tmp_path: Path) -> None:
    with patch.object(Path, "stat", side_effect=OSError("stat failed")):
        assert gate._modified_today(tmp_path / "debate.md") is False


@pytest.mark.parametrize(
    "merge_base",
    [None, _git_result("", returncode=1), _git_result("")],
)
def test_branch_history_requires_merge_base(
    tmp_path: Path,
    merge_base: subprocess.CompletedProcess[str] | None,
) -> None:
    debate = tmp_path / ".agents" / "analysis" / "debate.md"

    with patch.object(gate, "_run_git", return_value=merge_base):
        assert gate._modified_on_current_branch(tmp_path, debate) is False


def test_branch_history_accepts_path_changed_after_divergence(tmp_path: Path) -> None:
    debate = tmp_path / ".agents" / "analysis" / "debate.md"
    results = iter([_git_result("abc123\n"), _git_result("def456\n")])

    with patch.object(gate, "_run_git", side_effect=lambda *args: next(results)):
        assert gate._modified_on_current_branch(tmp_path, debate) is True


@pytest.mark.parametrize(
    "history",
    [None, _git_result("", returncode=1), _git_result("")],
)
def test_branch_history_rejects_path_unchanged_after_divergence(
    tmp_path: Path,
    history: subprocess.CompletedProcess[str] | None,
) -> None:
    debate = tmp_path / ".agents" / "analysis" / "debate.md"
    results = iter([_git_result("abc123\n"), history])

    with patch.object(gate, "_run_git", side_effect=lambda *args: next(results)):
        assert gate._modified_on_current_branch(tmp_path, debate) is False


def test_missing_analysis_directory_has_no_fresh_debate(tmp_path: Path) -> None:
    assert gate._has_fresh_debate_artifact(tmp_path) is False


def test_glob_failure_has_no_fresh_debate(tmp_path: Path) -> None:
    (tmp_path / ".agents" / "analysis").mkdir(parents=True)

    with patch.object(Path, "glob", side_effect=OSError("glob failed")):
        assert gate._has_fresh_debate_artifact(tmp_path) is False


def test_run_git_handles_timeout(tmp_path: Path) -> None:
    with patch.object(
        gate.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired("git", 5),
    ):
        assert gate._run_git(tmp_path, "status") is None


def test_run_git_decodes_with_utf8_replacement(tmp_path: Path) -> None:
    with patch.object(
        gate.subprocess,
        "run",
        return_value=_git_result("café\n"),
    ) as run:
        gate._run_git(tmp_path, "status")

    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"


def test_main_uses_git_worktree_root(tmp_path: Path) -> None:
    with patch.object(gate, "_run_git", return_value=_git_result(f"{tmp_path}\n")), patch.object(
        gate,
        "check_adr_review_evidence",
        return_value=2,
    ) as check:
        assert gate.main() == 2

    check.assert_called_once_with(tmp_path)


def test_main_fails_open_when_repo_root_is_unavailable() -> None:
    with patch.object(gate, "_run_git", return_value=None):
        assert gate.main() == 0


def test_script_entry_point_exits_with_main_result(tmp_path: Path) -> None:
    results = iter([_git_result(f"{tmp_path}\n"), _git_result("")])

    with patch.object(subprocess, "run", side_effect=lambda *args, **kwargs: next(results)):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(gate.__file__, run_name="__main__")

    assert exc_info.value.code == 0
