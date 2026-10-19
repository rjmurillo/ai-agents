"""Tests for scripts/eval/_durable_review.py, the reviewer arm contract (issue #5768).

Pure functions: the reply parser, the prompt, and the reviewer identity. The
drivers that launch the reviewer are tested in `test_durable_live.py` and
`test_eval_control_ablation.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _durable_review as review  # noqa: E402

MARKER = review.REVIEW_MARKER


def _reply(payload: str, *, before: str = "Notes on the change.") -> str:
    return f"{before}\n{MARKER} {payload}\n"


class TestParseReview:
    def test_an_empty_findings_list_is_a_measured_zero(self) -> None:
        assert review.parse_review(_reply('{"findings": []}')) == 0

    def test_each_finding_counts_once(self) -> None:
        assert review.parse_review(_reply('{"findings": ["a", "b", "c"]}')) == 3

    def test_only_the_last_marker_line_counts(self) -> None:
        text = f'{MARKER} {{"findings": ["old", "older"]}}\nRevised.\n{MARKER} {{"findings": []}}'
        assert review.parse_review(text) == 0

    def test_a_marker_quoted_mid_line_does_not_count(self) -> None:
        assert review.parse_review(f'I will end with {MARKER} {{"findings": []}} later.') is None

    def test_surrounding_whitespace_on_the_marker_line_is_tolerated(self) -> None:
        assert review.parse_review(f'   {MARKER}   {{"findings": ["x"]}}   ') == 1

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "Looks fine.",
            f"{MARKER}",
            f"{MARKER} not json",
            f"{MARKER} []",
            f"{MARKER} 3",
            f'{MARKER} {{"findings": "none"}}',
            f'{MARKER} {{"findings": null}}',
            f'{MARKER} {{"findings": [1, 2]}}',
            f'{MARKER} {{"findings": [""]}}',
            f'{MARKER} {{"findings": ["   "]}}',
            f'{MARKER} {{"findings": [], "note": "x"}}',
            f'{MARKER} {{"results": []}}',
        ],
    )
    def test_anything_else_is_missing_evidence_never_zero(self, text: str) -> None:
        assert review.parse_review(text) is None

    def test_a_truncated_reply_is_missing_evidence(self) -> None:
        assert review.parse_review(f'{MARKER} {{"findings": ["cut off') is None


class TestReviewerSpec:
    def test_identity_names_harness_model_and_effort(self) -> None:
        spec = review.ReviewerSpec("claude", "haiku", "low")
        assert spec.identity == "claude:haiku:low"
        assert review.reviewer_identity(spec) == "claude:haiku:low"

    def test_no_reviewer_is_none(self) -> None:
        assert review.reviewer_identity(None) == review.NO_REVIEWER == "none"

    @pytest.mark.parametrize(
        "fields",
        [("", "m", "low"), ("claude", " ", "low"), ("claude", "m", ""), ("a:b", "m", "low")],
    )
    def test_a_blank_or_colon_field_is_refused(self, fields: tuple[str, str, str]) -> None:
        with pytest.raises(ValueError, match="reviewer"):
            review.ReviewerSpec(*fields)

    def test_two_specs_that_differ_have_different_identities(self) -> None:
        low = review.ReviewerSpec("claude", "haiku", "low")
        high = review.ReviewerSpec("claude", "haiku", "high")
        assert low.identity != high.identity


class TestPrompt:
    def test_prompt_carries_the_requirement_paths_and_the_marker_instruction(self) -> None:
        prompt = review.review_prompt("Add subtract().", ["calc/core.py", "tests/test_core.py"])
        assert "Add subtract()." in prompt
        assert "- calc/core.py" in prompt and "- tests/test_core.py" in prompt
        assert MARKER in prompt

    def test_prompt_with_no_changed_paths_says_so(self) -> None:
        assert "(no changed paths)" in review.review_prompt("Do it.", [])

    def test_instructions_ask_for_the_marker_line_and_forbid_edits(self) -> None:
        text = review.REVIEWER_INSTRUCTIONS
        assert MARKER in text and "Do not edit files" in text and '{"findings": []}' in text

    def test_the_reviewer_tools_are_read_only(self) -> None:
        assert review.REVIEW_TOOLS == ("Read", "Glob", "Grep")
