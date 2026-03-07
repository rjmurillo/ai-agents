"""Tests for feature review parsing functions."""

from __future__ import annotations

import pytest

from scripts.ai_review_common.feature_review import (
    VALID_RECOMMENDATIONS,
    get_feature_review_assignees,
    get_feature_review_labels,
    get_feature_review_recommendation,
)


class TestGetFeatureReviewRecommendation:
    """Tests for get_feature_review_recommendation."""

    @pytest.mark.parametrize("recommendation", list(VALID_RECOMMENDATIONS))
    def test_extracts_explicit_recommendation(self, recommendation: str):
        output = f"RECOMMENDATION: {recommendation}\nRationale: some reason"
        result = get_feature_review_recommendation(output)
        assert result == recommendation

    def test_extracts_with_extra_whitespace(self):
        output = "RECOMMENDATION:   PROCEED  \nSome other text"
        assert get_feature_review_recommendation(output) == "PROCEED"

    def test_returns_unknown_for_empty_string(self):
        assert get_feature_review_recommendation("") == "UNKNOWN"

    def test_returns_unknown_for_whitespace_only(self):
        assert get_feature_review_recommendation("   \n\t  ") == "UNKNOWN"

    def test_returns_unknown_when_no_recommendation_found(self):
        output = "This is some text without a recommendation marker"
        assert get_feature_review_recommendation(output) == "UNKNOWN"

    def test_fallback_detects_proceed_keyword(self):
        output = "I recommend we PROCEED with this feature"
        assert get_feature_review_recommendation(output) == "PROCEED"

    def test_fallback_detects_decline_keyword(self):
        output = "We should DECLINE this request"
        assert get_feature_review_recommendation(output) == "DECLINE"

    def test_fallback_detects_defer_keyword(self):
        output = "Let's DEFER this to next quarter"
        assert get_feature_review_recommendation(output) == "DEFER"

    def test_decline_takes_priority_over_proceed_in_fallback(self):
        output = "If we PROCEED, we might need to DECLINE later"
        assert get_feature_review_recommendation(output) == "DECLINE"

    def test_explicit_recommendation_takes_priority(self):
        output = "RECOMMENDATION: PROCEED\nWe might DECLINE this later"
        assert get_feature_review_recommendation(output) == "PROCEED"


class TestGetFeatureReviewAssignees:
    """Tests for get_feature_review_assignees."""

    def test_extracts_single_username_with_at(self):
        output = "**Assignees**: @rjmurillo"
        assert get_feature_review_assignees(output) == "rjmurillo"

    def test_extracts_multiple_usernames(self):
        output = "**Assignees**: @user1, @user2, @user3"
        assert get_feature_review_assignees(output) == "user1,user2,user3"

    def test_handles_usernames_without_at_prefix(self):
        output = "Assignees: user1, user2"
        assert get_feature_review_assignees(output) == "user1,user2"

    def test_handles_plain_assignees_label(self):
        output = "Assignees: @dev-user"
        assert get_feature_review_assignees(output) == "dev-user"

    def test_returns_empty_for_none_suggested(self):
        output = "**Assignees**: none suggested"
        assert get_feature_review_assignees(output) == ""

    def test_returns_empty_for_no_one(self):
        output = "**Assignees**: no one"
        assert get_feature_review_assignees(output) == ""

    def test_returns_empty_for_na(self):
        output = "**Assignees**: n/a"
        assert get_feature_review_assignees(output) == ""

    def test_returns_empty_for_empty_string(self):
        assert get_feature_review_assignees("") == ""

    def test_returns_empty_for_whitespace(self):
        assert get_feature_review_assignees("   ") == ""

    def test_returns_empty_when_no_assignees_line(self):
        output = "Some other content without assignees"
        assert get_feature_review_assignees(output) == ""

    def test_filters_skip_words(self):
        output = "**Assignees**: @user1 or @user2"
        result = get_feature_review_assignees(output)
        assert "user1" in result
        assert "user2" in result
        assert "or" not in result


class TestGetFeatureReviewLabels:
    """Tests for get_feature_review_labels."""

    def test_extracts_backtick_wrapped_labels(self):
        output = "**Labels**: `enhancement`, `needs-design`"
        assert get_feature_review_labels(output) == "enhancement,needs-design"

    def test_extracts_plain_labels(self):
        output = "Labels: priority:P1, area-workflows"
        assert get_feature_review_labels(output) == "priority:P1,area-workflows"

    def test_handles_mixed_format(self):
        output = "**Labels**: `bug` and documentation"
        result = get_feature_review_labels(output)
        assert "bug" in result

    def test_returns_empty_for_none(self):
        output = "**Labels**: none"
        assert get_feature_review_labels(output) == ""

    def test_returns_empty_for_no_additional(self):
        output = "**Labels**: no additional"
        assert get_feature_review_labels(output) == ""

    def test_returns_empty_for_na(self):
        output = "**Labels**: n/a"
        assert get_feature_review_labels(output) == ""

    def test_returns_empty_for_empty_string(self):
        assert get_feature_review_labels("") == ""

    def test_returns_empty_for_whitespace(self):
        assert get_feature_review_labels("   ") == ""

    def test_returns_empty_when_no_labels_line(self):
        output = "Some other content without labels"
        assert get_feature_review_labels(output) == ""

    def test_filters_skip_words(self):
        output = "**Labels**: `bug` or `enhancement`"
        result = get_feature_review_labels(output)
        assert "bug" in result
        assert "enhancement" in result
        assert "or" not in result


class TestIntegration:
    """Integration tests with realistic AI output."""

    def test_parses_full_feature_review_output(self):
        output = """## Thank You

Thank you for this thoughtful feature request!

## Summary

This feature would add a review step to the issue triage workflow.

## Evaluation

| Criterion | Assessment | Confidence |
|-----------|------------|------------|
| User Impact | Medium | High |
| Implementation | Low | Medium |

## Recommendation

RECOMMENDATION: PROCEED

**Rationale**: Clear value proposition with manageable implementation.

## Suggested Actions

- **Assignees**: @rjmurillo, @dev-team
- **Labels**: `enhancement`, `area-workflows`
- **Milestone**: v0.4.0
- **Next Steps**:
  1. Create ADR for design decisions
  2. Implement parsing functions
"""
        assert get_feature_review_recommendation(output) == "PROCEED"
        assert get_feature_review_assignees(output) == "rjmurillo,dev-team"
        assert get_feature_review_labels(output) == "enhancement,area-workflows"

    def test_parses_decline_output(self):
        output = """## Thank You

Thanks for the suggestion.

## Recommendation

RECOMMENDATION: DECLINE

**Rationale**: Out of scope for current roadmap.

## Suggested Actions

- **Assignees**: none suggested
- **Labels**: none
- **Milestone**: backlog
"""
        assert get_feature_review_recommendation(output) == "DECLINE"
        assert get_feature_review_assignees(output) == ""
        assert get_feature_review_labels(output) == ""
