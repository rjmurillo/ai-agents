"""Report tests for check_review_thread_resolution_shas.py (issue #6195).

AC map: 6195-A3 diagnosable nesting fallback, 6195-A4 text mode field,
6195-A5 invalid reasons, failure reason, and git timeouts, 6195-A6 per-run
ancestry cache.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
sys.path.insert(0, str(_SCRIPTS_DIR))
try:
    import check_review_thread_resolution_shas as _mod
    import commit_ancestry
finally:
    sys.path.remove(str(_SCRIPTS_DIR))

_HEAD = "b" * 40
_DEEP_BODY = "\n".join(" " * (2 * depth) + "- x" for depth in range(40)) + " deadbee"


def _thread(thread_id: str, body: str, total: int = 1) -> dict[str, Any]:
    return {
        "id": thread_id,
        "isResolved": True,
        "path": "a.py",
        "line": 1,
        "comments": {
            "totalCount": total,
            "nodes": [
                {
                    "id": f"C-{thread_id}",
                    "databaseId": 1,
                    "body": body,
                    "author": {"login": "agent"},
                    "createdAt": "2026-10-11T00:00:00Z",
                }
            ],
        },
    }


def _report(*threads: dict[str, Any], complete: bool = True, result=(True, "reachable", "")):
    with patch.object(_mod, "check_ancestor", return_value=result) as ancestor:
        report = _mod.build_report("o", "r", 1, _HEAD, list(threads), complete, ".")
    return report, ancestor


def _git_stub(*results: subprocess.CompletedProcess[str] | BaseException):
    calls: list[dict[str, Any]] = []
    queue = list(results)

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, **kwargs})
        result = queue.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    return _run, calls


def _done(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def test_parsed_comment_reports_parsed_text_mode() -> None:
    # 6195-A4
    report, _ = _report(_thread("T1", "Fixed in abc1234"))
    assert report["references"][0]["text_mode"] == "parsed"
    assert report["raw_scan_comments"] == []


def test_nesting_fallback_is_recorded_per_reference_and_comment() -> None:
    # 6195-A3, 6195-A4
    report, _ = _report(_thread("T1", _DEEP_BODY))
    assert report["references"][0]["text_mode"] == "raw-nesting-limit"
    assert report["raw_scan_comments"] == [
        {"thread_id": "T1", "comment_id": "C-T1", "text_mode": "raw-nesting-limit"}
    ]


def test_raw_scan_is_listed_when_comment_has_no_sha() -> None:
    # 6195-A3: a raw scan that finds nothing is still visible in the report.
    body = "\n".join(" " * (2 * depth) + "- x" for depth in range(40))
    report, ancestor = _report(_thread("T1", body))
    assert report["sha_reference_count"] == 0
    assert report["raw_scan_comments"][0]["text_mode"] == "raw-nesting-limit"
    ancestor.assert_not_called()


def test_missing_parser_reports_raw_parser_missing_mode() -> None:
    # 6195-A4
    with patch.object(_mod, "_MARKDOWN", None):
        report, _ = _report(_thread("T1", "Fixed in abc1234"))
    assert report["references"][0]["text_mode"] == "raw-parser-missing"


def test_main_warns_on_nesting_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    # 6195-A3: the fallback is named on stderr with the comment that caused it.
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(
            _mod,
            "resolve_repo_params",
            return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
        ),
        patch.object(
            _mod, "fetch_review_threads", return_value=(_HEAD, [_thread("T1", _DEEP_BODY)], True)
        ),
        patch.object(_mod, "check_ancestor", return_value=(True, "reachable", "")),
    ):
        assert _mod.main(["--pull-request", "1"]) == 0
    captured = capsys.readouterr()
    assert "C-T1" in captured.err
    assert "raw-nesting-limit" in captured.err
    assert json.loads(captured.out)["raw_scan_comments"][0]["comment_id"] == "C-T1"


def test_main_is_quiet_when_every_comment_parses(capsys: pytest.CaptureFixture[str]) -> None:
    # 6195-A3 inverse: no warning when nothing fell back.
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(
            _mod,
            "resolve_repo_params",
            return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
        ),
        patch.object(
            _mod, "fetch_review_threads", return_value=(_HEAD, [_thread("T1", "abc1234")], True)
        ),
        patch.object(_mod, "check_ancestor", return_value=(True, "reachable", "")),
    ):
        assert _mod.main(["--pull-request", "1"]) == 0
    assert capsys.readouterr().err == ""


def test_same_sha_in_many_threads_is_checked_once() -> None:
    # 6195-A6
    threads = [_thread(f"T{index}", "Fixed in abc1234") for index in range(5)]
    report, ancestor = _report(*threads)
    ancestor.assert_called_once_with("abc1234", _HEAD, ".")
    assert report["sha_reference_count"] == 5
    assert report["reachable_count"] == 5


def test_distinct_shas_are_each_checked() -> None:
    # 6195-A6 inverse: the cache is keyed by SHA, not by run.
    report, ancestor = _report(_thread("T1", "abc1234"), _thread("T2", "def5678"))
    assert [call.args[0] for call in ancestor.call_args_list] == ["abc1234", "def5678"]
    assert report["sha_reference_count"] == 2


def test_git_error_counts_as_invalid_and_is_named() -> None:
    # 6195-A5: the gate still blocks; the report says why.
    report, _ = _report(_thread("T1", "abc1234"), result=(False, "invalid", "git-error: boom"))
    assert report["invalid_count"] == 1
    assert report["git_error_count"] == 1
    assert report["references"][0]["detail"] == "git-error: boom"


def test_missing_object_is_not_a_git_error() -> None:
    # 6195-A5
    report, _ = _report(_thread("T1", "abc1234"), result=(False, "invalid", "missing-object"))
    assert report["invalid_count"] == 1
    assert report["git_error_count"] == 0


def test_complete_fetch_has_no_failure_reason() -> None:
    # 6195-A5
    report, _ = _report(_thread("T1", "abc1234"))
    assert report["success"] is True
    assert report["failure_reason"] is None


def test_partial_comment_fetch_names_the_thread() -> None:
    # 6195-A5
    report, _ = _report(_thread("T1", "abc1234", total=2), complete=False)
    assert report["success"] is False
    assert "T1" in report["failure_reason"]


def test_partial_thread_fetch_names_pagination() -> None:
    # 6195-A5
    report, _ = _report(_thread("T1", "abc1234"), complete=False)
    assert "review thread pagination" in report["failure_reason"]


def test_partial_thread_and_comment_fetch_names_both() -> None:
    # 6195-A5
    report, _ = _report(_thread("T1", "abc1234", total=2), complete=False)
    assert "review thread pagination" in report["failure_reason"]
    assert "T1" in report["failure_reason"]


def test_partial_comment_fetch_with_complete_pages_fails() -> None:
    # 6195-A5
    report, _ = _report(_thread("T1", "abc1234", total=2))
    assert report["success"] is False
    assert report["fetched_pages_complete"] is False
    assert "review thread pagination" not in report["failure_reason"]


def test_check_ancestor_reports_missing_object() -> None:
    # 6195-A5
    run, calls = _git_stub(_done(1), _done(0, stdout=""))
    with patch("subprocess.run", side_effect=run):
        assert _mod.check_ancestor("abc1234", _HEAD, ".") == (False, "invalid", "missing-object")
    assert all(call["timeout"] == commit_ancestry._GIT_TIMEOUT_SECONDS for call in calls)


def test_check_ancestor_reports_non_commit_object() -> None:
    # 6195-A5
    run, _ = _git_stub(_done(1), _done(0, stdout="abc1234ffff\n"))
    with patch("subprocess.run", side_effect=run):
        assert _mod.check_ancestor("abc1234", _HEAD, ".") == (False, "invalid", "not-a-commit")


def test_check_ancestor_reports_ambiguous_count() -> None:
    # 6195-A5
    run, _ = _git_stub(_done(1), _done(0, stdout="abc1234a\nabc1234b\n"))
    with patch("subprocess.run", side_effect=run):
        reachable, status, detail = _mod.check_ancestor("abc1234", _HEAD, ".")
    assert (reachable, status) == (False, "ambiguous")
    assert detail.startswith("2 ")


@pytest.mark.parametrize(
    "results",
    [
        (_done(128, stderr="fatal: not a git repository\nmore"),),
        (_done(1), _done(129, stderr="fatal: bad option\n")),
        (_done(0, stdout="abc1234\n"), _done(128, stderr="fatal: Not a valid commit name\n")),
    ],
    ids=["verify", "disambiguate", "merge-base"],
)
def test_check_ancestor_names_git_errors(results: tuple[subprocess.CompletedProcess[str]]) -> None:
    # 6195-A5: a git failure is invalid (gate blocks) and carries git's message.
    run, _ = _git_stub(*results)
    with patch("subprocess.run", side_effect=run):
        reachable, status, detail = _mod.check_ancestor("abc1234", _HEAD, ".")
    assert (reachable, status) == (False, "invalid")
    assert detail.startswith("git-error: fatal: ")
    assert "\n" not in detail


@pytest.mark.parametrize(
    "error",
    [subprocess.TimeoutExpired(["git"], 30), FileNotFoundError("git")],
    ids=["timeout", "no-git"],
)
def test_check_ancestor_survives_git_that_cannot_run(error: BaseException) -> None:
    # 6195-A5: a hung or missing git is a named git error, not a crash.
    run, _ = _git_stub(error)
    with patch("subprocess.run", side_effect=run):
        reachable, status, detail = _mod.check_ancestor("abc1234", _HEAD, ".")
    assert (reachable, status) == (False, "invalid")
    assert detail.startswith("git-error: ")
