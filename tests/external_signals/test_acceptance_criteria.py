"""Tests for scripts.external_signals.acceptance_criteria."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.external_signals import acceptance_criteria as ac
from scripts.external_signals import markdown_visibility as mv

BODY_OK = """\
# Title

## Acceptance

- [x] Adds `external_signals` helper module
- [x] Returns deterministic verdict

## Notes

unrelated
"""

BODY_MIXED = """\
## Acceptance Criteria

- [ ] Add validator
- [x] Document the contract
"""

BODY_NONE = """\
# Random doc

No acceptance section here.
"""


def test_parse_criteria_extracts_section():
    crits = ac.parse_criteria(BODY_OK)
    assert [c.text for c in crits] == [
        "Adds `external_signals` helper module",
        "Returns deterministic verdict",
    ]
    assert all(c.checked for c in crits)


def test_parse_criteria_mixed_check_state():
    crits = ac.parse_criteria(BODY_MIXED)
    assert [c.checked for c in crits] == [False, True]


def test_parse_criteria_no_section():
    assert ac.parse_criteria(BODY_NONE) == []


def test_evaluate_pass_all_checked():
    report = ac.evaluate(BODY_OK)
    assert report.passed
    assert report.unchecked == []


def test_evaluate_fails_when_unchecked():
    report = ac.evaluate(BODY_MIXED)
    assert not report.passed
    assert report.unchecked == ["Add validator"]


def test_diff_misses_flags_unmatched():
    body = "## Acceptance\n\n- [x] Implement `widget_factory` helper\n"
    diff = "+++ b/scripts/other.py\n+def something(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == ["Implement `widget_factory` helper"]


def test_diff_misses_clears_when_keyword_present():
    body = "## Acceptance\n\n- [x] Implement widget_factory helper\n"
    diff = "+++ b/scripts/x.py\n+def widget_factory(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == []


def test_diff_misses_ignores_deleted_lines():
    """Keyword in a deleted line must not satisfy the criterion."""
    body = "## Acceptance\n\n- [x] Add api endpoint\n"
    # The keyword 'api' only appears on a deleted line, not an added one.
    diff = "+++ b/scripts/x.py\n-def api(): pass\n+def other(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == ["Add api endpoint"]


def test_diff_misses_matches_added_lines_only():
    """Keyword in an added line satisfies the criterion."""
    body = "## Acceptance\n\n- [x] Add api endpoint\n"
    diff = "+++ b/scripts/x.py\n-def old(): pass\n+def api(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == []


def test_keywords_includes_three_char_tech_terms():
    """3-char technical terms like 'api', 'cli', 'git' must be extracted."""
    assert "api" in ac._keywords("Add API endpoint")
    assert "cli" in ac._keywords("cli command")
    assert "git" in ac._keywords("git commit")


def test_keywords_excludes_stop_words():
    """Common 3-char stop words like 'the', 'and', 'for' must be excluded."""
    assert "the" not in ac._keywords("fix the bug")
    assert "and" not in ac._keywords("add and remove")
    assert "for" not in ac._keywords("run for testing")


def test_keywords_short_criterion_not_silently_skipped():
    """A criterion with only short tech terms should still match the diff."""
    body = "## Acceptance\n\n- [x] Add CLI\n"
    diff = "+++ b/scripts/x.py\n+cli_main()\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == []


def test_cli_fails_when_no_criteria(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    body = tmp_path / "body.md"
    body.write_text(BODY_NONE, encoding="utf-8")
    rc = ac.main(["--body", str(body)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no acceptance criteria" in err


def test_cli_allow_empty(tmp_path: Path):
    body = tmp_path / "body.md"
    body.write_text(BODY_NONE, encoding="utf-8")
    assert ac.main(["--body", str(body), "--allow-empty"]) == 0


def test_cli_json_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    body = tmp_path / "body.md"
    body.write_text(BODY_OK, encoding="utf-8")
    rc = ac.main(["--body", str(body), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"passed": true' in out


def test_cli_unreadable_body_is_config_error(tmp_path: Path):
    missing = tmp_path / "nope.md"
    with pytest.raises(SystemExit) as exc:
        ac.main(["--body", str(missing)])
    assert exc.value.code == 2


def test_pr_template_acceptance_section_parses() -> None:
    """The shipped PR template must stay parseable by this module.

    push-pr.md requires an ``## Acceptance criteria`` section that the
    Validate Spec Coverage job reads through parse_criteria. The template
    gained that section in PR 5095 after drifting apart from the validator
    (issue 5068); this test pins the contract so a template edit that
    renames or drops the section fails here instead of silently reviving
    the drift.
    """
    template = Path(__file__).resolve().parents[2] / ".github" / "PULL_REQUEST_TEMPLATE.md"
    body = template.read_text(encoding="utf-8")

    section = ac.extract_acceptance_section(body)
    criteria = ac.parse_criteria(body)

    assert section.strip(), "template lost its ## Acceptance criteria section"
    assert len(criteria) >= 1
    # The placeholder must be visible prose, not an HTML comment: a rendered
    # empty checkbox with no text hides the fill-me-in signal from authors.
    assert all("<!--" not in c.text for c in criteria)


def test_subheadings_inside_the_section_keep_their_boxes() -> None:
    body = (
        "## Acceptance criteria\n\n### Group A\n- [x] one\n\n### Group B\n- [ ] two\n\n"
        "## Notes\n- [ ] not a criterion\n"
    )

    crits = ac.parse_criteria(body)

    assert [c.text for c in crits] == ["one", "two"]


def test_section_ends_at_a_heading_of_the_same_level() -> None:
    body = "## Acceptance\n- [x] a\n## Other\n- [ ] b\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a"]


def test_section_ends_at_a_higher_level_heading() -> None:
    body = "### Acceptance\n- [x] a\n## Other\n- [ ] b\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a"]


def test_deeper_heading_does_not_end_the_section_but_sibling_does() -> None:
    body = "## Acceptance\n#### deep\n- [x] a\n## Next\n- [ ] b\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a"]


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_checkboxes_in_fenced_code_are_ignored(fence: str) -> None:
    body = f"## Acceptance\n- [x] real\n{fence}\n- [ ] example\n{fence}\n- [x] after\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["real", "after"]


def test_heading_inside_a_fence_does_not_end_the_section() -> None:
    body = "## Acceptance\n```bash\n# a shell comment\n```\n- [ ] still here\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["still here"]


def test_shorter_or_other_char_fence_does_not_close() -> None:
    body = "## Acceptance\n````\n```\n~~~\n- [ ] hidden\n````\n- [x] shown\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["shown"]


def test_unclosed_fence_hides_the_rest() -> None:
    body = "## Acceptance\n- [x] a\n```\n- [ ] hidden\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a"]


def test_checkboxes_in_html_comments_are_ignored() -> None:
    body = "## Acceptance\n<!-- one-line - [ ] x -->\n<!--\n- [ ] multi\nline\n-->\n- [x] real\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["real"]


def test_comment_opener_inside_a_fence_does_not_hide_later_boxes() -> None:
    body = "## Acceptance\n- [x] one\n```\n<!-- x\n```\n- [ ] two\n"
    assert [(c.text, c.checked) for c in ac.parse_criteria(body)] == [
        ("one", True),
        ("two", False),
    ]


def test_comment_opener_inside_a_code_span_is_literal() -> None:
    body = "## Acceptance\n- [x] see `<!--` and ``a ` <!-- b``\n- [ ] later\n"
    assert [(c.text, c.checked) for c in ac.parse_criteria(body)] == [
        ("see `<!--` and ``a ` <!-- b``", True),
        ("later", False),
    ]


def test_unmatched_backtick_does_not_hide_a_real_comment() -> None:
    body = "## Acceptance\n- [x] a ` b <!-- - [ ] gone --> c\n- [ ] kept\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a ` b  c", "kept"]


def test_text_after_a_closed_inline_comment_stays_visible() -> None:
    body = "## Acceptance\n- [ ] a <!-- b --> c\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a  c"]


def test_comment_closed_on_a_later_line_keeps_the_tail_of_that_line() -> None:
    body = "## Acceptance\n<!--\nhidden\n--> \n- [ ] shown\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["shown"]


def test_fence_opener_inside_a_comment_does_not_hide_later_boxes() -> None:
    body = "## Acceptance\n<!--\n```python\nexample()\n-->\n- [x] real\n- [ ] open\n"
    assert [(c.text, c.checked) for c in ac.parse_criteria(body)] == [
        ("real", True),
        ("open", False),
    ]


def test_acceptance_heading_inside_a_comment_or_fence_is_not_a_section() -> None:
    assert ac.parse_criteria("<!--\n## Acceptance\n- [ ] x\n-->\n") == []
    assert ac.parse_criteria("```\n## Acceptance\n- [ ] x\n```\n") == []


def test_fenced_unchecked_box_does_not_fail_the_report() -> None:
    body = "## Acceptance\n- [x] real\n```\n- [ ] example\n```\n"
    assert ac.evaluate(body).passed


def test_fence_line_with_an_info_string_does_not_close_the_fence() -> None:
    body = "## Acceptance\n```\n```python\n- [ ] example\n```\n- [x] real\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["real"]


def test_closing_fence_may_carry_trailing_whitespace() -> None:
    body = "## Acceptance\n```\n- [ ] hidden\n```   \n- [x] real\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["real"]


def test_unclosed_html_comment_hides_the_rest() -> None:
    body = "## Acceptance\n- [x] a\n<!-- never closed\n- [ ] hidden\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a"]


def test_closed_comment_followed_by_text_still_shows_text() -> None:
    body = "## Acceptance\n<!-- c --> \n- [x] a\n"
    assert [c.text for c in ac.parse_criteria(body)] == ["a"]


def test_unclosed_comment_is_reported() -> None:
    assert mv.unclosed_construct("## Acceptance\n- [x] a\n<!-- stray\n- [ ] b\n") == "comment"


def test_unclosed_fence_is_reported() -> None:
    assert mv.unclosed_construct("## Acceptance\n- [x] a\n```\n- [ ] b\n") == "fence"


def test_closed_constructs_report_nothing() -> None:
    body = "## Acceptance\n<!-- c -->\n```\nx\n```\n- [x] a\n"
    assert mv.unclosed_construct(body) is None


def test_comment_hidden_by_a_multiline_span_is_reported_unclosed() -> None:
    body = "## Acceptance\n- [x] done `code\n  continued <!-- note` here\n- [ ] pending\n"
    assert mv.unclosed_construct(body) == "comment"


def test_escaped_backtick_does_not_open_a_code_span() -> None:
    body = "## Acceptance\n\\`<!-- `\n- [x] hid\n-->\n- [ ] v\n"
    assert [(c.text, c.checked) for c in ac.parse_criteria(body)] == [("v", False)]


def test_hidden_unchecked_box_in_the_section_is_reported() -> None:
    body = "## Acceptance\n- [x] a\n<!--\n- [ ] commented out\n-->\n"
    assert ac.hidden_unchecked(body) == ["commented out"]


def test_closed_span_differential_is_reported_not_passed() -> None:
    body = "## Acceptance\n- [x] done `code\n  continued <!-- note` here\n- [ ] pending\n-->\n"
    assert ac.hidden_unchecked(body) == ["pending"]


def test_hidden_checked_box_is_not_reported() -> None:
    body = "## Acceptance\n- [x] a\n<!-- - [x] b -->\n```\n- [x] c\n```\n"
    assert ac.hidden_unchecked(body) == []


def test_hidden_box_outside_the_section_is_not_reported() -> None:
    body = "## Notes\n```\n- [ ] example\n```\n## Acceptance\n- [x] a\n## Other\n<!-- - [ ] x -->\n"
    assert ac.hidden_unchecked(body) == []


def test_prose_mentioning_a_checkbox_inside_a_comment_is_not_a_box() -> None:
    body = "## Acceptance\n<!--\nUse `- [ ]` checkboxes here.\n-->\n- [x] a\n"
    assert ac.hidden_unchecked(body) == []


def test_minimal_comment_closes_on_its_own_line() -> None:
    body = "## Acceptance\n- [x] a\n<!-->\n- [ ] pending\n"
    assert [(c.text, c.checked) for c in ac.parse_criteria(body)] == [
        ("a", True),
        ("pending", False),
    ]


def test_backtick_fence_info_with_a_backtick_is_not_a_fence() -> None:
    body = "``` a`b\n## Acceptance\n- [ ] x\n"
    assert [(c.text, c.checked) for c in ac.parse_criteria(body)] == [("x", False)]


def test_tilde_fence_info_may_hold_a_backtick() -> None:
    assert ac.parse_criteria("~~~ a`b\n## Acceptance\n- [ ] x\n~~~\n") == []


def test_acceptance_headings_are_counted_in_the_raw_body() -> None:
    body = "```\n## Acceptance\n- [ ] x\n```\n## Acceptance criteria\n- [x] y\n"
    assert ac.acceptance_heading_count(body) == 2
    assert ac.acceptance_heading_count("## Acceptance\n- [x] y\n") == 1


def test_has_acceptance_section_true_for_accepted_heading() -> None:
    assert ac.has_acceptance_section("## Acceptance criteria\n\n1. one\n")


def test_has_acceptance_section_false_for_suffixed_heading() -> None:
    assert not ac.has_acceptance_section("## Acceptance criteria (draft)\n\n- [x] one\n")


def test_has_acceptance_section_false_when_absent() -> None:
    assert not ac.has_acceptance_section("prose only")


def test_near_miss_headings_lists_rejected_headings_only() -> None:
    body = "## Acceptance criteria\n\n## Acceptance criteria (draft)\n\n### 2. Acceptance\n"
    assert ac.near_miss_headings(body) == ["## Acceptance criteria (draft)", "### 2. Acceptance"]


def test_near_miss_headings_ignores_hidden_and_non_heading_lines() -> None:
    body = "see acceptance below\n<!--\n## Acceptance (old)\n-->\n```\n## Acceptance (x)\n```\n"
    assert ac.near_miss_headings(body) == []
