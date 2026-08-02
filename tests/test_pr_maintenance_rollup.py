"""Tests for shared PR maintenance status rollup helpers."""

from __future__ import annotations

import pytest

from scripts import pr_maintenance_rollup


@pytest.mark.parametrize(
    "conclusion",
    [
        "ACTION_REQUIRED",
        "CANCELLED",
        "FAILURE",
        "STALE",
        "STARTUP_FAILURE",
        "TIMED_OUT",
    ],
)
def test_check_run_failure_conclusions_are_failing(conclusion: str) -> None:
    assert pr_maintenance_rollup.context_is_failing({"conclusion": conclusion})


@pytest.mark.parametrize("conclusion", [None, "NEUTRAL", "SKIPPED", "SUCCESS"])
def test_non_failure_check_run_conclusions_are_not_failing(
    conclusion: str | None,
) -> None:
    assert not pr_maintenance_rollup.context_is_failing({"conclusion": conclusion})


def test_status_context_error_is_failing() -> None:
    assert pr_maintenance_rollup.context_is_failing({"state": "ERROR"})


@pytest.mark.parametrize(
    ("total_count", "has_next_page", "expected_incomplete"),
    [
        (2, False, False),
        (3, True, True),
    ],
)
def test_page_limit_uses_final_page_state(
    monkeypatch: pytest.MonkeyPatch,
    total_count: int,
    has_next_page: bool,
    expected_incomplete: bool,
) -> None:
    monkeypatch.setattr(pr_maintenance_rollup, "_CONTEXTS_MAX_PAGES", 1)
    contexts = {
        "totalCount": total_count,
        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
        "nodes": [{"name": "first", "conclusion": "SUCCESS"}],
    }
    prs = [
        {
            "commits": {
                "nodes": [
                    {
                        "commit": {
                            "oid": "abc123",
                            "statusCheckRollup": {"contexts": contexts},
                        }
                    }
                ]
            }
        }
    ]

    pr_maintenance_rollup.complete_status_check_rollups(
        "owner",
        "repo",
        prs,
        lambda *_: (
            [{"name": "second", "conclusion": "SUCCESS"}],
            {"hasNextPage": has_next_page, "endCursor": "cursor-2"},
        ),
    )

    assert contexts["__incomplete"] is expected_incomplete
