"""Behavior pins for the get_pr_review_comments orchestration refactor."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from .pr_review_comments_behavior_helpers import (
    _issue_comment,
    _review_comment,
    _stale_detection_subprocess,
    grc,
)


def test_comments_are_sorted_by_created_at_across_review_and_issue():
    review = [
        _review_comment(3, "2024-01-03T00:00:00Z"),
        _review_comment(1, "2024-01-01T00:00:00Z"),
    ]
    issue = [_issue_comment(2, "2024-01-02T00:00:00Z")]

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[review, issue],
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            include_issue_comments=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [1, 2, 3]
    assert result["ReviewCommentCount"] == 2
    assert result["IssueCommentCount"] == 1


def test_equal_created_at_keeps_review_comments_before_issue_comments():
    created = "2024-01-01T00:00:00Z"
    review = [
        _review_comment(1, created),
        _review_comment(2, created),
    ]
    issue = [_issue_comment(3, created)]

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[review, issue],
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            include_issue_comments=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [1, 2, 3]


def test_group_by_domain_keeps_sorted_order_inside_domain_buckets():
    review = [
        _review_comment(3, "2024-01-03T00:00:00Z", body="SQL injection risk"),
        _review_comment(1, "2024-01-01T00:00:00Z", body="This will crash"),
        _review_comment(2, "2024-01-02T00:00:00Z", body="Authentication is missing"),
    ]

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        return_value=review,
    ):
        result = grc.get_pr_review_comments("o", "r", 42, group_by_domain=True)

    assert [comment["Id"] for comment in result["Security"]] == [2, 3]
    assert [comment["Id"] for comment in result["Bug"]] == [1]
    assert result["DomainCounts"] == {
        "Security": 2,
        "Bug": 1,
        "Style": 0,
        "Summary": 0,
        "General": 0,
    }


def test_only_stale_returns_deleted_and_out_of_range_comments_only():
    review = [
        _review_comment(1, "2024-01-01T00:00:00Z", path="deleted.py", line=1),
        _review_comment(2, "2024-01-02T00:00:00Z", line=99),
        _review_comment(3, "2024-01-03T00:00:00Z", line=2),
    ]
    content = "print('start')\nprint('ok')\nprint('end')\n"

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=_stale_detection_subprocess(content),
        ),
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            detect_stale=True,
            only_stale=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [1, 2]
    assert [comment["StaleReason"] for comment in result["Comments"]] == [
        "FileDeleted",
        "LineOutOfRange",
    ]
    assert result["StaleCount"] == 2


def test_exclude_stale_keeps_current_code_comment():
    review = [
        _review_comment(1, "2024-01-01T00:00:00Z", path="deleted.py", line=1),
        _review_comment(3, "2024-01-03T00:00:00Z", line=2),
    ]
    content = "print('start')\nprint('ok')\nprint('end')\n"

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=_stale_detection_subprocess(content),
        ),
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            detect_stale=True,
            exclude_stale=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [3]
    assert result["Comments"][0]["Stale"] is False
    assert result["StaleCount"] == 0


def test_code_changed_stale_reason_has_matching_context_control():
    review = [
        _review_comment(
            1,
            "2024-01-01T00:00:00Z",
            diff_hunk=" old_context\n+missing_call()\n",
        ),
        _review_comment(2, "2024-01-02T00:00:00Z"),
    ]
    content = "print('start')\nprint('ok')\nprint('end')\n"

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=_stale_detection_subprocess(content),
        ),
    ):
        result = grc.get_pr_review_comments("o", "r", 42, detect_stale=True)

    states = {
        comment["Id"]: (comment["Stale"], comment["StaleReason"]) for comment in result["Comments"]
    }
    assert states == {
        1: (True, "CodeChanged"),
        2: (False, None),
    }


def test_include_diff_hunk_controls_diff_hunk_field():
    review = [_review_comment(1, "2024-01-01T00:00:00Z")]

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        return_value=review,
    ):
        without_hunk = grc.get_pr_review_comments("o", "r", 42)

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        return_value=review,
    ):
        with_hunk = grc.get_pr_review_comments("o", "r", 42, include_diff_hunk=True)

    assert without_hunk["Comments"][0]["DiffHunk"] is None
    assert with_hunk["Comments"][0]["DiffHunk"] == " context\n+print('ok')\n"


def test_unaddressed_acknowledged_unresolved_comment_is_marked_acknowledged():
    review = [_review_comment(1, "2024-01-01T00:00:00Z", eyes=1)]
    unresolved = [{"comments": {"nodes": [{"databaseId": 1}]}}]

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.get_unresolved_review_threads",
            return_value=unresolved,
        ),
    ):
        result = grc.get_pr_review_comments("o", "r", 42, only_unaddressed=True)

    assert result["TotalComments"] == 1
    assert result["Comments"][0]["LifecycleState"] == "ACKNOWLEDGED"


def test_unaddressed_lifecycle_truth_table_includes_new_and_excludes_resolved_acknowledged():
    created = "2024-01-01T00:00:00Z"
    review = [
        _review_comment(1, created, eyes=0),
        _review_comment(2, created, eyes=0),
        _review_comment(3, created, eyes=1),
        _review_comment(4, created, eyes=1),
    ]
    unresolved = [
        {"comments": {"nodes": [{"databaseId": 1}]}},
        {"comments": {"nodes": [{"databaseId": 3}]}},
    ]

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.get_unresolved_review_threads",
            return_value=unresolved,
        ),
    ):
        result = grc.get_pr_review_comments("o", "r", 42, only_unaddressed=True)

    assert [comment["Id"] for comment in result["Comments"]] == [1, 2, 3]
    assert [comment["LifecycleState"] for comment in result["Comments"]] == [
        "NEW",
        "NEW",
        "ACKNOWLEDGED",
    ]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["--pull-request", "42", "--exclude-stale"],
            "--exclude-stale requires --detect-stale",
        ),
        (
            ["--pull-request", "42", "--only-stale"],
            "--only-stale requires --detect-stale",
        ),
        (
            ["--pull-request", "42", "--detect-stale", "--exclude-stale", "--only-stale"],
            "--exclude-stale and --only-stale are mutually exclusive",
        ),
        (
            ["--pull-request", "42", "--bot-only"],
            "--bot-only requires --only-unaddressed",
        ),
    ],
)
def test_invalid_flag_combinations_return_one_before_authentication(argv, message, capsys):
    with patch("grc_behavior_under_test.assert_gh_authenticated") as authenticated:
        rc = grc.main(argv)

    assert rc == 1
    assert message in capsys.readouterr().err
    authenticated.assert_not_called()


def test_review_comment_api_failure_exits_three(capsys):
    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(SystemExit) as exc:
            grc.get_pr_review_comments("o", "r", 42)

    assert exc.value.code == 3
    assert "Failed to fetch PR review comments" in capsys.readouterr().err
