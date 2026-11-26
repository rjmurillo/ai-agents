"""Contract pins for get_pr_review_comments output and filtering edges."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from .pr_review_comments_behavior_helpers import (
    _empty_tree_subprocess,
    _issue_comment,
    _review_comment,
    _stale_detection_subprocess,
    grc,
)


def test_standard_output_shape_counts_replies_domains_and_authors(capsys):
    first = _review_comment(
        1,
        "2024-01-01T00:00:00Z",
        author="alice",
        body="SQL injection risk",
    )
    reply = _review_comment(
        2,
        "2024-01-02T00:00:00Z",
        author="bob",
        body="This will crash",
        in_reply_to=1,
    )
    third = _review_comment(
        3,
        "2024-01-03T00:00:00Z",
        author="alice",
        body="formatting cleanup",
    )

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        return_value=[third, reply, first],
    ):
        result = grc.get_pr_review_comments("o", "r", 42)

    def expected_comment(comment, domain):
        return {
            "Id": comment["id"],
            "CommentType": "Review",
            "Author": comment["user"]["login"],
            "AuthorType": comment["user"]["type"],
            "Path": comment["path"],
            "Line": comment["line"],
            "Side": comment["side"],
            "Body": comment["body"],
            "Domain": domain,
            "CreatedAt": comment["created_at"],
            "UpdatedAt": comment["updated_at"],
            "InReplyToId": comment["in_reply_to_id"],
            "IsReply": comment["in_reply_to_id"] is not None,
            "DiffHunk": None,
            "HtmlUrl": comment["html_url"],
            "CommitId": comment["commit_id"],
            "Stale": None,
            "StaleReason": None,
            "EyesCount": 0,
        }

    assert result == {
        "Success": True,
        "PullRequest": 42,
        "Owner": "o",
        "Repo": "r",
        "TotalComments": 3,
        "ReviewCommentCount": 3,
        "IssueCommentCount": 0,
        "TopLevelCount": 2,
        "ReplyCount": 1,
        "StaleCount": 0,
        "DomainCounts": {
            "security": 1,
            "bug": 1,
            "style": 1,
            "summary": 0,
            "general": 0,
        },
        "AuthorSummary": [
            {"Author": "alice", "Count": 2},
            {"Author": "bob", "Count": 1},
        ],
        "Comments": [
            expected_comment(first, "security"),
            expected_comment(reply, "bug"),
            expected_comment(third, "style"),
        ],
    }
    assert capsys.readouterr().err == (
        "PR #42: 3 review comments | Domains: Security(1), Bug(1), Style(1)\n"
    )


def test_grouped_output_stderr_summaries(capsys):
    review = [
        _review_comment(
            1,
            "2024-01-01T00:00:00Z",
            author="alice",
            body="SQL injection risk",
        ),
        _review_comment(
            2,
            "2024-01-02T00:00:00Z",
            author="bob",
            body="This will crash",
        ),
    ]

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        return_value=review,
    ):
        grc.get_pr_review_comments("o", "r", 42, group_by_domain=True)

    assert capsys.readouterr().err == (
        "PR #42: Grouped by domain: Security(1), Bug(1), Style(0), Summary(0), General(0)\n"
    )

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        return_value=review,
    ):
        grc.get_pr_review_comments("o", "r", 42, group_by_reviewer_priority=True)

    assert capsys.readouterr().err == (
        "PR #42: Grouped by reviewer priority: P0(0), P1(2), P2(0), Unknown(0)\n"
    )


def test_empty_file_tree_warns_and_marks_path_comments_file_deleted(capsys):
    review = [_review_comment(1, "2024-01-01T00:00:00Z")]

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            return_value=review,
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=_empty_tree_subprocess,
        ),
    ):
        result = grc.get_pr_review_comments("o", "r", 42, detect_stale=True)

    assert result["Comments"][0]["Stale"] is True
    assert result["Comments"][0]["StaleReason"] == "FileDeleted"
    assert "WARNING: File tree is empty. Stale detection disabled." in capsys.readouterr().err


def test_issue_comment_stale_flag_follows_detect_stale():
    issue = [_issue_comment(1, "2024-01-01T00:00:00Z")]

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            side_effect=[[], issue],
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=_stale_detection_subprocess("print('ok')\n"),
        ),
    ):
        detected = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            include_issue_comments=True,
            detect_stale=True,
        )

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[[], issue],
    ):
        undetected = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            include_issue_comments=True,
        )

    assert detected["Comments"][0]["Stale"] is False
    assert undetected["Comments"][0]["Stale"] is None


def test_only_stale_drops_issue_comments():
    review = [
        _review_comment(1, "2024-01-01T00:00:00Z", path="deleted.py", line=1),
    ]
    issue = [_issue_comment(2, "2024-01-02T00:00:00Z")]

    with (
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            side_effect=[review, issue],
        ),
        patch(
            "grc_behavior_under_test.subprocess.run",
            side_effect=_stale_detection_subprocess("print('ok')\n"),
        ),
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            include_issue_comments=True,
            detect_stale=True,
            only_stale=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [1]
    assert result["Comments"][0]["CommentType"] == "Review"
    assert result["StaleCount"] == 1


def test_author_filter_applies_to_review_and_issue_comments():
    review = [
        _review_comment(1, "2024-01-01T00:00:00Z", author="alice"),
        _review_comment(2, "2024-01-02T00:00:00Z", author="bob"),
    ]
    issue = [
        _issue_comment(3, "2024-01-03T00:00:00Z", author="alice"),
        _issue_comment(4, "2024-01-04T00:00:00Z", author="bob"),
    ]

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[review, issue],
    ):
        result = grc.get_pr_review_comments(
            "o",
            "r",
            42,
            author="alice",
            include_issue_comments=True,
        )

    assert [comment["Id"] for comment in result["Comments"]] == [1, 3]
    assert [comment["CommentType"] for comment in result["Comments"]] == ["Review", "Issue"]
    assert result["ReviewCommentCount"] == 1
    assert result["IssueCommentCount"] == 1


def test_issue_comment_api_failure_exits_three(capsys):
    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[[], RuntimeError("boom")],
    ):
        with pytest.raises(SystemExit) as exc:
            grc.get_pr_review_comments("o", "r", 42, include_issue_comments=True)

    assert exc.value.code == 3
    assert "Failed to fetch issue comments for PR #42" in capsys.readouterr().err


def test_paginated_comment_system_exit_passes_through(capsys):
    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[[], SystemExit(4)],
    ):
        with pytest.raises(SystemExit) as exc:
            grc.get_pr_review_comments("o", "r", 42, include_issue_comments=True)

    assert exc.value.code == 4
    assert "Failed to fetch issue comments" not in capsys.readouterr().err
