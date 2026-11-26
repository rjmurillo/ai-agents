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
    issue = _issue_comment(
        4,
        "2024-01-04T00:00:00Z",
        author="carol",
    )

    with patch(
        "grc_behavior_under_test.gh_api_paginated",
        side_effect=[[third, reply, first], [issue]],
    ):
        result = grc.get_pr_review_comments("o", "r", 42, include_issue_comments=True)

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

    expected_issue = {
        "Id": issue["id"],
        "CommentType": "Issue",
        "Author": issue["user"]["login"],
        "AuthorType": issue["user"]["type"],
        "Path": None,
        "Line": None,
        "Side": None,
        "Body": issue["body"],
        "Domain": "general",
        "CreatedAt": issue["created_at"],
        "UpdatedAt": issue["updated_at"],
        "InReplyToId": None,
        "IsReply": False,
        "DiffHunk": None,
        "HtmlUrl": issue["html_url"],
        "CommitId": None,
        "Stale": None,
        "StaleReason": None,
        "EyesCount": 0,
    }

    assert result == {
        "Success": True,
        "PullRequest": 42,
        "Owner": "o",
        "Repo": "r",
        "TotalComments": 4,
        "ReviewCommentCount": 3,
        "IssueCommentCount": 1,
        "TopLevelCount": 3,
        "ReplyCount": 1,
        "StaleCount": 0,
        "DomainCounts": {
            "security": 1,
            "bug": 1,
            "style": 1,
            "summary": 0,
            "general": 1,
        },
        "AuthorSummary": [
            {"Author": "alice", "Count": 2},
            {"Author": "bob", "Count": 1},
            {"Author": "carol", "Count": 1},
        ],
        "Comments": [
            expected_comment(first, "security"),
            expected_comment(reply, "bug"),
            expected_comment(third, "style"),
            expected_issue,
        ],
    }
    assert capsys.readouterr().err == (
        "PR #42: 3 review comments + 1 issue comment | "
        "Domains: Security(1), Bug(1), Style(1), General(1)\n"
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


@pytest.mark.parametrize(
    ("count", "include_issue", "detect_stale", "expected"),
    [
        (1, True, True, "PR #42: 1 review comment + 1 issue comment (1 stale comment)"),
        (2, True, True, "PR #42: 2 review comments + 2 issue comments (2 stale comments)"),
        (1, True, False, "PR #42: 1 review comment + 1 issue comment"),
        (2, True, False, "PR #42: 2 review comments + 2 issue comments"),
        (1, False, True, "PR #42: 1 review comment (1 stale comment)"),
        (2, False, True, "PR #42: 2 review comments (2 stale comments)"),
    ],
)
def test_standard_stderr_issue_and_stale_segments(
    capsys, count, include_issue, detect_stale, expected
):
    review = [
        _review_comment(i, "2024-01-01T00:00:00Z", path="deleted.py", line=1)
        for i in range(1, count + 1)
    ]
    issue = [_issue_comment(10 + i, "2024-01-02T00:00:00Z") for i in range(count)]
    patches = [
        patch(
            "grc_behavior_under_test.gh_api_paginated",
            side_effect=[review, issue] if include_issue else [review],
        )
    ]
    if detect_stale:
        patches.append(
            patch(
                "grc_behavior_under_test.subprocess.run",
                side_effect=_stale_detection_subprocess("print('ok')\n"),
            )
        )

    with patches[0]:
        if detect_stale:
            with patches[1]:
                grc.get_pr_review_comments(
                    "o",
                    "r",
                    42,
                    include_issue_comments=include_issue,
                    detect_stale=detect_stale,
                )
        else:
            grc.get_pr_review_comments(
                "o",
                "r",
                42,
                include_issue_comments=include_issue,
                detect_stale=detect_stale,
            )

    assert capsys.readouterr().err.startswith(expected)


def test_standard_output_key_and_author_summary_order():
    comments = [
        _review_comment(1, "2024-01-01T00:00:00Z", author="bob"),
        _review_comment(2, "2024-01-02T00:00:00Z", author="alice"),
        _review_comment(3, "2024-01-03T00:00:00Z", author="bob"),
        _review_comment(4, "2024-01-04T00:00:00Z", author="carol"),
        _review_comment(5, "2024-01-05T00:00:00Z", author="carol"),
        _review_comment(6, "2024-01-06T00:00:00Z", author="carol"),
    ]

    with patch("grc_behavior_under_test.gh_api_paginated", return_value=comments):
        result = grc.get_pr_review_comments("o", "r", 42)

    assert list(result) == [
        "Success",
        "PullRequest",
        "Owner",
        "Repo",
        "TotalComments",
        "ReviewCommentCount",
        "IssueCommentCount",
        "TopLevelCount",
        "ReplyCount",
        "StaleCount",
        "DomainCounts",
        "AuthorSummary",
        "Comments",
    ]
    assert list(result["DomainCounts"]) == ["security", "bug", "style", "summary", "general"]
    assert [entry["Author"] for entry in result["AuthorSummary"]] == ["bob", "alice", "carol"]
