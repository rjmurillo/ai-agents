"""Actions run ID tests for check_review_thread_resolution_shas.py (issue #6767)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
sys.path.insert(0, str(_SCRIPTS_DIR))

import check_review_thread_resolution_shas as _mod  # noqa: E402


def _thread(thread_id: str, resolved: bool, body: str) -> dict:
    return {
        "id": thread_id,
        "isResolved": resolved,
        "path": "src/app.py",
        "line": 12,
        "comments": {
            "totalCount": 1,
            "nodes": [
                {
                    "id": "C1",
                    "databaseId": 1,
                    "body": body,
                    "author": {"login": "agent"},
                    "createdAt": "2026-08-03T00:00:01Z",
                }
            ],
        },
    }


def test_actions_run_id_is_not_a_sha() -> None:
    assert _mod.extract_shas("Evidence: run 39223031239 passed.") == []


def test_actions_run_url_ids_are_not_shas() -> None:
    body = "See https://github.com/o/r/actions/runs/39223031239/job/10234567890 for logs."
    assert _mod.extract_shas(body) == []


def test_run_id_does_not_hide_adjacent_sha() -> None:
    body = "Fixed in abc1234, verified by run 39223031239 and run 39223031240."
    assert _mod.extract_shas(body) == ["abc1234"]


def test_bare_run_id_without_keyword_is_not_a_sha() -> None:
    assert _mod.extract_shas("Evidence: 39223031239 and 39223031240") == []


def test_run_keyword_forms_mark_run_ids() -> None:
    for text in (
        "run 1234567",
        "Run ID 1234567",
        "run #1234567",
        "run: 1234567",
        "actions/runs/1234567",
    ):
        assert _mod.extract_shas(text) == [], text


def test_run_id_after_punctuation_is_not_a_sha() -> None:
    for text in (
        "run (123456789) passed",
        "run `1234567`",
        "run=1234567",
        "run - 123456789",
        "run-1234567",
        'run "1234567"',
    ):
        assert _mod.extract_shas(text) == [], text


def test_sentence_break_after_run_is_not_run_context() -> None:
    assert _mod.extract_shas("It was a run. 1234567 fixed it") == ["1234567"]


def test_short_digit_sha_without_run_context_is_checked() -> None:
    assert _mod.extract_shas("Fixed in 1234567") == ["1234567"]


def test_rerun_keyword_is_not_run_context() -> None:
    assert _mod.extract_shas("rerun 1234567") == ["1234567"]


def test_hex_token_with_letters_is_still_a_sha() -> None:
    assert _mod.extract_shas("39223031239a then abc1234") == ["39223031239a", "abc1234"]


def test_resolved_thread_citing_run_ids_passes_report() -> None:
    thread = _thread("T1", True, "Fixed in abc1234. CI: run 39223031239, run 39223031240.")
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(True, "reachable", ""),
    ) as check:
        report = _mod.build_report("o", "r", 1, "b" * 40, [thread], True, ".")
    assert [call.args[0] for call in check.call_args_list] == ["abc1234"]
    assert report["sha_reference_count"] == 1
    assert report["invalid_count"] == 0
    assert report["reachable_count"] == 1


def test_label_of_actions_run_link_is_not_a_sha() -> None:
    body = "See [123456789](https://github.com/o/r/actions/runs/123456789) for logs."
    assert _mod.extract_shas(body) == []


def test_label_of_commit_link_is_still_checked() -> None:
    body = "See [1234567](https://github.com/o/r/commit/1234567abcdef) for the fix."
    assert _mod.extract_shas(body) == ["1234567abcdef", "1234567"]


def test_label_of_other_link_is_still_checked() -> None:
    assert _mod.extract_shas("See [1234567](https://example.com/page).") == ["1234567"]
