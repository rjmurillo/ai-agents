"""Tests for the deterministic PR commit-churn classifier (scripts/eval/_pr_churn.py).

Behavior under test: priority-ordered bucket classification, histogram counting,
and the thrash fraction. Pure functions, so no mocking is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "eval"))

import _pr_churn  # noqa: E402


@pytest.mark.parametrize(
    "headline, expected",
    [
        ("revert: undo bad merge", "revert"),
        ("Merge branch 'main' into feature/x", "merge_rebase"),
        ("fix(ci): align memory-validation workflow", "ci_fix"),
        ("style: fix markdownlint trailing whitespace", "lint_format"),
        ("docs(session): finalize session 906", "validation_protocol"),
        ("fix: address cursor[bot] review feedback", "review_response"),
        ("test(pr-maintenance): add unit tests for bot authority", "test_fix"),
        ("chore(deps): bump anthropic to v0.107.0", "deps"),
        ("feat(memory): implement confidence scoring", "progress"),
    ],
)
def test_classify_assigns_each_bucket(headline: str, expected: str) -> None:
    # Arrange / Act
    result = _pr_churn.classify(headline)

    # Assert
    assert result == expected


def test_classify_returns_other_for_unmatched() -> None:
    assert _pr_churn.classify("something entirely unrelated zzz") == "other"


def test_classify_handles_empty_headline() -> None:
    assert _pr_churn.classify("") == "other"


@pytest.mark.parametrize(
    "headline, expected",
    [
        ("run gh act locally", "ci_fix"),
        ("run gh-act locally", "ci_fix"),
        ("fix session log evidence", "validation_protocol"),
        ("fix session-log evidence", "validation_protocol"),
        ("fix pre-pr gate", "validation_protocol"),
    ],
)
def test_classify_allows_explicit_optional_separators(headline: str, expected: str) -> None:
    assert _pr_churn.classify(headline) == expected


@pytest.mark.parametrize("headline", ["ghXact", "sessionXlog", "preXpr"])
def test_classify_separator_tokens_do_not_match_arbitrary_characters(headline: str) -> None:
    assert _pr_churn.classify(headline) == "other"


def test_classify_priority_merge_beats_ci() -> None:
    # A merge commit that also mentions ci must land in merge_rebase (higher priority).
    assert _pr_churn.classify("Merge branch 'main' to fix ci") == "merge_rebase"


def test_classify_priority_revert_is_highest() -> None:
    assert _pr_churn.classify("revert: feat that broke the build") == "revert"


def test_histogram_counts_and_omits_empty_buckets() -> None:
    # Arrange
    headlines = [
        "feat: a",
        "feat: b",
        "fix(ci): c",
        "docs(session): d",
    ]

    # Act
    counts = _pr_churn.histogram(headlines)

    # Assert
    assert counts == {"progress": 2, "ci_fix": 1, "validation_protocol": 1}
    assert "merge_rebase" not in counts


def test_thrash_fraction_empty_is_zero() -> None:
    assert _pr_churn.thrash_fraction([]) == 0.0


def test_thrash_fraction_all_progress_is_zero() -> None:
    assert _pr_churn.thrash_fraction(["feat: a", "feat: b"]) == 0.0


def test_thrash_fraction_all_thrash_is_one() -> None:
    assert _pr_churn.thrash_fraction(["docs(session): a", "fix(ci): b"]) == 1.0


def test_thrash_fraction_mixed() -> None:
    # 1 progress of 4 -> 0.75 thrash.
    headlines = ["feat: a", "docs(session): b", "fix(ci): c", "Merge branch 'main'"]
    assert _pr_churn.thrash_fraction(headlines) == 0.75


def test_churn_buckets_contract() -> None:
    # The public bucket list ends with the residual and contains every rule name.
    assert _pr_churn.CHURN_BUCKETS[-1] == "other"
    assert "validation_protocol" in _pr_churn.CHURN_BUCKETS
    assert "progress" in _pr_churn.CHURN_BUCKETS
