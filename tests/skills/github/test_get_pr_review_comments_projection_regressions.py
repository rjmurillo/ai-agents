"""Regression pins for get_pr_review_comments projection edges."""

from __future__ import annotations

from unittest.mock import call, patch

from .pr_review_comments_behavior_helpers import (
    _issue_comment,
    _review_comment,
    _stale_detection_subprocess,
    grc,
)


def test_include_issue_comments_fetches_review_then_issue_endpoints():
    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[[], []],
    ) as fetch:
        grc.get_pr_review_comments("o", "r", 42, include_issue_comments=True)

    assert fetch.call_args_list == [
        call("repos/o/r/pulls/42/comments"),
        call("repos/o/r/issues/42/comments"),
    ]


def test_stale_detection_reuses_content_cache_at_pr_head():
    review = [
        _review_comment(1, "2024-01-01T00:00:00Z"),
        _review_comment(2, "2024-01-02T00:00:00Z"),
    ]
    content = "print('start')\nprint('ok')\nprint('end')\n"
    endpoints = []
    stale_subprocess = _stale_detection_subprocess(content)

    def record_subprocess(cmd, *args, **kwargs):
        endpoints.append(cmd[2])
        return stale_subprocess(cmd, *args, **kwargs)

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=record_subprocess,
        ),
    ):
        result = grc.get_pr_review_comments("o", "r", 42, detect_stale=True)

    assert [comment["Stale"] for comment in result["Comments"]] == [False, False]
    content_requests = [
        endpoint for endpoint in endpoints if endpoint.startswith("repos/o/r/contents/")
    ]
    assert content_requests == ["repos/o/r/contents/src%2Fmain.py?ref=abc123"]


def test_only_unaddressed_excludes_acknowledged_issue_comment():
    issue = [
        _issue_comment(1, "2024-01-01T00:00:00Z", eyes=1),
        _issue_comment(2, "2024-01-02T00:00:00Z"),
    ]

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            side_effect=[[], issue],
        ),
        patch(
            "grc_behavior_under_test.get_unresolved_review_threads",
            return_value=[],
        ),
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            include_issue_comments=True,
            only_unaddressed=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [2]
    assert result["Comments"][0]["LifecycleState"] == "NEW"


def test_original_line_fallback_marks_out_of_range_comment_stale():
    review_comment = _review_comment(1, "2024-01-01T00:00:00Z", line=99)
    review_comment["line"] = None
    review_comment["original_line"] = 99
    content = "print('start')\nprint('ok')\nprint('end')\n"

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=[review_comment],
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

    assert [comment["Id"] for comment in result["Comments"]] == [1]
    assert result["Comments"][0]["Line"] == 99
    assert result["Comments"][0]["StaleReason"] == "LineOutOfRange"
    assert result["StaleCount"] == 1
