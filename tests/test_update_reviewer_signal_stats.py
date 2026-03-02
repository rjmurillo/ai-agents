"""Tests for scripts/update_reviewer_signal_stats.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.update_reviewer_signal_stats import (
    HEURISTICS,
    MEMORY_PATH,
    SELF_COMMENT_EXCLUDED_AUTHORS,
    TREND_THRESHOLDS,
    ActionabilityResult,
    CommentData,
    ReviewerStats,
    SignalStats,
    get_actionability_score,
    get_comments_by_reviewer,
    get_reviewer_signal_stats,
    update_serena_memory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_comment(
    body: str,
    author: str = "reviewer1",
    created_at: str | None = None,
    is_resolved: bool = False,
    thread_comments: list[dict[str, Any]] | None = None,
) -> CommentData:
    """Build a CommentData for testing."""
    if created_at is None:
        created_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    return CommentData(
        pr_number=1,
        body=body,
        created_at=created_at,
        path="file.py",
        is_resolved=is_resolved,
        is_outdated=False,
        thread_comments=thread_comments or [],
    )


def _make_pr(
    number: int,
    author: str,
    comments: list[tuple[str, str]],
    is_resolved: bool = False,
) -> dict[str, Any]:
    """Build a PR dict matching GraphQL shape.

    Args:
        number: PR number.
        author: PR author login.
        comments: List of (comment_author, comment_body) tuples.
        is_resolved: Whether the thread is resolved.
    """
    comment_nodes = [
        {
            "id": f"c{i}",
            "body": body,
            "author": {"login": comment_author},
            "createdAt": datetime.now(UTC).isoformat(),
            "path": "file.py",
        }
        for i, (comment_author, body) in enumerate(comments)
    ]

    return {
        "number": number,
        "author": {"login": author},
        "reviewThreads": {
            "nodes": [
                {
                    "isResolved": is_resolved,
                    "isOutdated": False,
                    "comments": {"nodes": comment_nodes},
                }
            ]
        },
    }


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Verify module-level configuration constants."""

    def test_self_comment_excluded_authors(self) -> None:
        assert "dependabot[bot]" in SELF_COMMENT_EXCLUDED_AUTHORS

    def test_heuristics_fixed_in_reply_positive(self) -> None:
        assert HEURISTICS["fixed_in_reply"] > 0

    def test_heuristics_severity_low_negative(self) -> None:
        assert HEURISTICS["severity_low"] < 0

    def test_heuristics_contains_all_keys(self) -> None:
        expected_keys = {
            "fixed_in_reply",
            "wont_fix_reply",
            "severity_high",
            "potential_null",
            "severity_low",
            "unused_remove",
            "no_reply_after_days",
            "no_reply_threshold",
        }
        assert expected_keys == set(HEURISTICS.keys())

    def test_memory_path(self) -> None:
        assert MEMORY_PATH == ".serena/memories/pr-comment-responder-skills.md"

    def test_trend_thresholds(self) -> None:
        assert TREND_THRESHOLDS["improving"] == 0.05
        assert TREND_THRESHOLDS["declining"] == -0.05


# ---------------------------------------------------------------------------
# Actionability scoring tests
# ---------------------------------------------------------------------------


class TestActionabilityScore:
    """Test get_actionability_score function."""

    def test_neutral_comment_score_around_half(self) -> None:
        comment = _make_comment("This is a neutral comment", is_resolved=True)
        result = get_actionability_score(comment)
        assert 0.4 <= result.score <= 0.6

    def test_fixed_in_reply_increases_score(self) -> None:
        comment = _make_comment(
            "This needs to be fixed",
            is_resolved=True,
            thread_comments=[{"body": "Fixed in commit abc123"}],
        )
        result = get_actionability_score(comment)
        assert result.score > 0.5
        assert "FixedInReply" in result.reasons

    def test_security_comment_increases_score(self) -> None:
        comment = _make_comment("This has a CWE-22 vulnerability")
        result = get_actionability_score(comment)
        assert result.score > 0.5
        assert "SeverityHigh" in result.reasons

    def test_unused_comment_decreases_score(self) -> None:
        comment = _make_comment("This variable is unused and should be removed")
        result = get_actionability_score(comment)
        assert result.score < 0.5
        assert "UnusedRemove" in result.reasons

    def test_nit_comment_decreases_score(self) -> None:
        comment = _make_comment("nit: consider using a different variable name")
        result = get_actionability_score(comment)
        assert result.score < 0.5
        assert "SeverityLow" in result.reasons

    def test_score_clamped_between_0_and_1(self) -> None:
        # Very negative comment: multiple negative signals
        comment = _make_comment(
            "nit: unused code to remove, minor cosmetic issue",
            created_at=(datetime.now(UTC) - timedelta(days=30)).isoformat(),
        )
        result = get_actionability_score(comment)
        assert result.score >= 0.0
        assert result.score <= 1.0

    def test_is_actionable_true_when_score_gte_half(self) -> None:
        comment = _make_comment("Critical security vulnerability")
        result = get_actionability_score(comment)
        assert result.is_actionable is True

    def test_is_actionable_false_for_low_signal(self) -> None:
        comment = _make_comment("nit: minor style issue")
        result = get_actionability_score(comment)
        assert result.is_actionable is False

    def test_no_reply_after_days_penalty(self) -> None:
        old_date = (datetime.now(UTC) - timedelta(days=14)).isoformat()
        comment = _make_comment(
            "This is a neutral comment",
            created_at=old_date,
            is_resolved=False,
        )
        result = get_actionability_score(comment)
        assert "NoReplyAfterDays" in result.reasons

    def test_no_reply_penalty_skipped_for_resolved(self) -> None:
        old_date = (datetime.now(UTC) - timedelta(days=14)).isoformat()
        comment = _make_comment(
            "This is a neutral comment",
            created_at=old_date,
            is_resolved=True,
        )
        result = get_actionability_score(comment)
        assert "NoReplyAfterDays" not in result.reasons

    def test_wontfix_reply_increases_score(self) -> None:
        comment = _make_comment(
            "This might be an issue",
            thread_comments=[{"body": "Won't fix, this is intentional"}],
        )
        result = get_actionability_score(comment)
        assert result.score > 0.5
        assert "WontFixReply" in result.reasons

    def test_potential_null_increases_score(self) -> None:
        comment = _make_comment("potential null reference here")
        result = get_actionability_score(comment)
        assert "PotentialNull" in result.reasons
        assert result.score > 0.5

    def test_result_is_actionability_result(self) -> None:
        comment = _make_comment("test")
        result = get_actionability_score(comment)
        assert isinstance(result, ActionabilityResult)


# ---------------------------------------------------------------------------
# Comments by reviewer tests
# ---------------------------------------------------------------------------


class TestCommentsByReviewer:
    """Test get_comments_by_reviewer function."""

    def test_groups_by_reviewer_login(self) -> None:
        prs = [_make_pr(1, "author1", [("reviewer1", "Comment 1")])]
        result = get_comments_by_reviewer(prs)
        assert "reviewer1" in result
        assert result["reviewer1"].total_comments == 1

    def test_excludes_self_comments(self) -> None:
        prs = [_make_pr(1, "author1", [("author1", "Self-comment")])]
        result = get_comments_by_reviewer(prs)
        assert "author1" not in result

    def test_allows_cross_author_reviews(self) -> None:
        prs = [_make_pr(1, "someone", [("rjmurillo", "Review comment")])]
        result = get_comments_by_reviewer(prs)
        assert "rjmurillo" in result
        assert result["rjmurillo"].total_comments == 1

    def test_tracks_unique_prs(self) -> None:
        prs = [
            _make_pr(
                1,
                "author1",
                [("reviewer1", "Comment 1"), ("reviewer1", "Comment 2")],
            )
        ]
        result = get_comments_by_reviewer(prs)
        assert result["reviewer1"].total_comments == 2
        assert len(result["reviewer1"].prs_with_comments) == 1

    def test_dependabot_self_comments_excluded(self) -> None:
        prs = [
            _make_pr(
                1,
                "dependabot[bot]",
                [("dependabot[bot]", "Dependabot commenting on its own PR")],
            )
        ]
        result = get_comments_by_reviewer(prs)
        assert "dependabot[bot]" not in result

    def test_dependabot_reviewing_others_included(self) -> None:
        # dependabot reviewing someone else's PR (unusual but should work)
        prs = [_make_pr(1, "human-author", [("dependabot[bot]", "Review")])]
        result = get_comments_by_reviewer(prs)
        assert "dependabot[bot]" in result

    def test_multiple_prs_multiple_reviewers(self) -> None:
        prs = [
            _make_pr(1, "author1", [("reviewer1", "C1"), ("reviewer2", "C2")]),
            _make_pr(2, "author2", [("reviewer1", "C3")]),
        ]
        result = get_comments_by_reviewer(prs)
        assert result["reviewer1"].total_comments == 2
        assert len(result["reviewer1"].prs_with_comments) == 2
        assert result["reviewer2"].total_comments == 1

    def test_empty_prs_returns_empty(self) -> None:
        result = get_comments_by_reviewer([])
        assert result == {}

    def test_comments_are_comment_data_instances(self) -> None:
        prs = [_make_pr(1, "author1", [("reviewer1", "Comment")])]
        result = get_comments_by_reviewer(prs)
        assert isinstance(result["reviewer1"].comments[0], CommentData)


# ---------------------------------------------------------------------------
# Reviewer signal stats tests
# ---------------------------------------------------------------------------


class TestReviewerSignalStats:
    """Test get_reviewer_signal_stats function."""

    def test_calculates_signal_rate(self) -> None:
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        reviewer_stats = {
            "reviewer1": ReviewerStats(
                total_comments=2,
                prs_with_comments={1},
                comments=[
                    _make_comment("Critical security issue", created_at=recent),
                    _make_comment("nit: minor style issue", created_at=recent),
                ],
            ),
        }
        result = get_reviewer_signal_stats(reviewer_stats)
        assert result["reviewer1"].total_comments == 2
        assert 0.0 <= result["reviewer1"].signal_rate <= 1.0

    def test_stable_trend_for_small_samples(self) -> None:
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        reviewer_stats = {
            "reviewer1": ReviewerStats(
                total_comments=3,
                prs_with_comments={1},
                comments=[
                    _make_comment("Comment 1", created_at=recent),
                ],
            ),
        }
        result = get_reviewer_signal_stats(reviewer_stats)
        assert result["reviewer1"].trend == "stable"

    def test_signal_stats_type(self) -> None:
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        reviewer_stats = {
            "reviewer1": ReviewerStats(
                total_comments=1,
                prs_with_comments={1},
                comments=[_make_comment("Comment", created_at=recent)],
            ),
        }
        result = get_reviewer_signal_stats(reviewer_stats)
        assert isinstance(result["reviewer1"], SignalStats)

    def test_empty_comments_zero_rate(self) -> None:
        reviewer_stats = {
            "reviewer1": ReviewerStats(
                total_comments=0,
                prs_with_comments=set(),
                comments=[],
            ),
        }
        result = get_reviewer_signal_stats(reviewer_stats)
        assert result["reviewer1"].signal_rate == 0.0

    def test_prs_with_comments_count(self) -> None:
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        reviewer_stats = {
            "reviewer1": ReviewerStats(
                total_comments=2,
                prs_with_comments={1, 2},
                comments=[
                    _make_comment("C1", created_at=recent),
                    _make_comment("C2", created_at=recent),
                ],
            ),
        }
        result = get_reviewer_signal_stats(reviewer_stats)
        assert result["reviewer1"].prs_with_comments == 2


# ---------------------------------------------------------------------------
# Serena memory update tests
# ---------------------------------------------------------------------------


class TestUpdateSerenaMemory:
    """Test update_serena_memory function."""

    @pytest.fixture()
    def memory_file(self, tmp_path: Path) -> Path:
        """Create a test memory file."""
        content = (
            "# PR Comment Responder Skills Memory\n"
            "\n"
            "## Overview\n"
            "\n"
            "Memory for tracking reviewer signal quality statistics.\n"
            "\n"
            "## Per-Reviewer Performance (Cumulative)\n"
            "\n"
            "| Reviewer | PRs | Comments | Actionable | Signal | Notes |\n"
            "|----------|-----|----------|------------|--------|-------|\n"
            "| old-reviewer | 1 | 1 | 1 | 100% | Old data |\n"
            "\n"
            "## Per-PR Breakdown\n"
            "\n"
            "Details here.\n"
        )
        path = tmp_path / "test-memory.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_updates_per_reviewer_table(self, memory_file: Path) -> None:
        stats = {
            "reviewer1": SignalStats(
                total_comments=10,
                prs_with_comments=5,
                verified_actionable=8,
                estimated_actionable=8,
                signal_rate=0.8,
                trend="stable",
                last_30_days_comments=3,
                last_30_days_signal_rate=0.9,
            ),
        }

        result = update_serena_memory(stats, 10, 30, str(memory_file))

        assert result is True
        content = memory_file.read_text(encoding="utf-8")
        assert "reviewer1" in content
        assert "80%" in content

    def test_sorts_by_signal_rate_descending(self, memory_file: Path) -> None:
        stats = {
            "low_signal": SignalStats(
                total_comments=10,
                prs_with_comments=3,
                verified_actionable=0,
                estimated_actionable=3,
                signal_rate=0.3,
                trend="stable",
                last_30_days_comments=0,
                last_30_days_signal_rate=0.0,
            ),
            "high_signal": SignalStats(
                total_comments=10,
                prs_with_comments=5,
                verified_actionable=0,
                estimated_actionable=9,
                signal_rate=0.9,
                trend="stable",
                last_30_days_comments=0,
                last_30_days_signal_rate=0.0,
            ),
        }

        update_serena_memory(stats, 5, 30, str(memory_file))

        content = memory_file.read_text(encoding="utf-8")
        high_pos = content.index("high_signal")
        low_pos = content.index("low_signal")
        assert high_pos < low_pos

    def test_returns_false_if_file_missing(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "non-existent.md"
        result = update_serena_memory({}, 0, 0, str(non_existent))
        assert result is False

    def test_high_signal_gets_bold(self, memory_file: Path) -> None:
        stats = {
            "star_reviewer": SignalStats(
                total_comments=10,
                prs_with_comments=5,
                verified_actionable=0,
                estimated_actionable=10,
                signal_rate=0.95,
                trend="improving",
                last_30_days_comments=0,
                last_30_days_signal_rate=0.0,
            ),
        }

        update_serena_memory(stats, 10, 30, str(memory_file))

        content = memory_file.read_text(encoding="utf-8")
        assert "**95%**" in content

    def test_trend_icons(self, memory_file: Path) -> None:
        stats = {
            "improving_reviewer": SignalStats(
                total_comments=10,
                prs_with_comments=5,
                verified_actionable=0,
                estimated_actionable=8,
                signal_rate=0.8,
                trend="improving",
                last_30_days_comments=0,
                last_30_days_signal_rate=0.0,
            ),
            "declining_reviewer": SignalStats(
                total_comments=10,
                prs_with_comments=5,
                verified_actionable=0,
                estimated_actionable=5,
                signal_rate=0.5,
                trend="declining",
                last_30_days_comments=0,
                last_30_days_signal_rate=0.0,
            ),
        }

        update_serena_memory(stats, 10, 30, str(memory_file))

        content = memory_file.read_text(encoding="utf-8")
        assert "\u2191" in content  # improving arrow
        assert "\u2193" in content  # declining arrow

    def test_preserves_other_sections(self, memory_file: Path) -> None:
        stats = {
            "reviewer1": SignalStats(
                total_comments=5,
                prs_with_comments=2,
                verified_actionable=0,
                estimated_actionable=3,
                signal_rate=0.6,
                trend="stable",
                last_30_days_comments=0,
                last_30_days_signal_rate=0.0,
            ),
        }

        update_serena_memory(stats, 5, 30, str(memory_file))

        content = memory_file.read_text(encoding="utf-8")
        assert "## Overview" in content
        assert "## Per-PR Breakdown" in content
        assert "Details here." in content

    def test_empty_stats_produces_empty_table(self, memory_file: Path) -> None:
        update_serena_memory({}, 0, 30, str(memory_file))

        content = memory_file.read_text(encoding="utf-8")
        assert "## Per-Reviewer Performance (Cumulative)" in content
        assert "Aggregated from 0 PRs over last 30 days." in content
