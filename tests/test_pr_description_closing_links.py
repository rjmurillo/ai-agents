"""Tests for validate_closing_links in pr_description.py (issue #3827).

Covers:
- Positive: bare Fixes #N on own line -> no issues
- Positive: Closes / Resolves / Fix / Close / Resolve variants
- Negative: closing keyword inside inline code span -> CRITICAL
- Negative: closing keyword inside fenced code block -> CRITICAL
- Edge: closing keyword in blockquote -> no issue (blockquotes are valid)
- Edge: Refs #N (non-closing keyword) in code span -> no issue
- Edge: stacked PR (non-default base) with closing keyword -> WARNING
- Edge: stacked PR with no closing keyword -> no issue
- Edge: keyword inside nested backtick span in list item -> CRITICAL
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "validation" / "pr_description.py"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("pr_description_closing_links_test")
validate_closing_links = _mod.validate_closing_links


class TestBareKeywordIsValid:
    """Bare closing keywords on their own line are honored by GitHub."""

    def test_fixes_on_own_line(self):
        body = "Some description.\n\nFixes #42\n"
        issues = validate_closing_links(body, "main", "main")
        assert issues == []

    def test_closes_variant(self):
        body = "Closes #100"
        assert validate_closing_links(body, "main", "main") == []

    def test_resolves_variant(self):
        body = "Resolves #7"
        assert validate_closing_links(body, "main", "main") == []

    def test_fix_variant(self):
        body = "Fix #5"
        assert validate_closing_links(body, "main", "main") == []

    def test_close_variant(self):
        body = "Close #5"
        assert validate_closing_links(body, "main", "main") == []

    def test_resolve_variant(self):
        body = "Resolve #5"
        assert validate_closing_links(body, "main", "main") == []

    def test_fixed_variant(self):
        body = "Fixed #12"
        assert validate_closing_links(body, "main", "main") == []

    def test_refs_not_a_closing_keyword(self):
        # Refs #N is not a closing keyword - no issue even inside code span
        body = "`Refs #42`"
        assert validate_closing_links(body, "main", "main") == []


class TestInlineCodeSpan:
    """Closing keyword inside backtick code span should be CRITICAL."""

    def test_fixes_in_backtick_is_critical(self):
        body = "Added scan. `Fixes #3770`."
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert issues[0].issue_type == "Closing keyword in inline code span"
        # The literal issue number must be in the message
        assert "3770" in issues[0].message or "Fixes" in issues[0].message

    def test_closes_in_backtick_is_critical(self):
        body = "`Closes #99`"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_resolves_in_backtick_is_critical(self):
        body = "See `Resolves #7` for context."
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_list_item_with_backtick_fixes(self):
        body = "- `Fixes #3747`: fixed the bug"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_multiple_backtick_keywords(self):
        body = "`Fixes #1` and `Closes #2`"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 2
        for i in issues:
            assert i.severity == "CRITICAL"

    def test_double_backtick_span_is_detected(self):
        """Double-backtick code spans must be caught (issue #3827)."""
        body = "Adds a scan. ``Fixes #123``."
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert "inline code span" in issues[0].issue_type

    def test_triple_backtick_inline_span(self):
        """Triple-backtick inline span (not a fence) is also caught."""
        body = "See ```Closes #456``` for details."
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_multiline_triple_backtick_inline_span_is_caught(self):
        """CommonMark 0.31.2 6.1 allows a code span to cross lines for any
        delimiter length, not just short runs; confining the 3+ backtick
        branch to a single line missed this and read the keyword as a
        genuine bare claim (Copilot, PR #5371 round 4)."""
        body = "See ```example\nFixes #4965\nend``` for details."
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert "inline code span" in issues[0].issue_type

    def test_backtick_fence_opener_with_backtick_in_info_string_is_not_a_fence(self):
        """CommonMark 0.31.2 4.5: a backtick fence's info string must not
        itself contain a backtick; an opener that does isn't a fence at
        all, so text after it is ordinary prose, not fenced content
        (Copilot, PR #5371 round 4)."""
        body = "```lang`x`\nFixes #4965\n"
        assert validate_closing_links(body, "main", "main") == []


class TestFencedCodeBlock:
    """Closing keyword inside a fenced block should be CRITICAL."""

    def test_keyword_in_triple_backtick_fence(self):
        body = "Example:\n```\nFixes #42\n```\n"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert issues[0].issue_type == "Closing keyword in fenced code block"

    def test_keyword_in_tilde_fence(self):
        body = "~~~\nCloses #10\n~~~\n"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_keyword_after_fence_is_clean(self):
        body = "```\nsome code\n```\nFixes #5\n"
        assert validate_closing_links(body, "main", "main") == []

    def test_keyword_in_code_block_with_lang_tag(self):
        body = "```markdown\nFixes #42\n```\n"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_tilde_fence_info_string_may_contain_a_backtick(self):
        """CommonMark 0.31.2 4.5 restricts backticks in the info string to
        backtick fences only; a tilde fence's info string is unrestricted,
        so this must still open a real fence (Copilot, PR #5371 round 4)."""
        body = "~~~lang`x`\nFixes #42\n~~~\n"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert issues[0].issue_type == "Closing keyword in fenced code block"

    def test_unclosed_backtick_fence_still_reports_the_keyword_as_fenced(self):
        """CommonMark 0.31.2 4.5: an unclosed fence still runs to EOF (Copilot, PR #5371)."""
        body = "```\nFixes #42"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert issues[0].issue_type == "Closing keyword in fenced code block"

    def test_unclosed_tilde_fence_still_reports_the_keyword_as_fenced(self):
        body = "~~~\nCloses #10"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_fence_indented_up_to_three_spaces_is_still_a_fence(self):
        """CommonMark 0.31.2 4.5 permits up to 3 spaces of indent on both
        fences; the keyword inside must still be reported as fenced, not
        read as ordinary un-indented text outside any span."""
        body = "  ```\n  Fixes #42\n  ```\n"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"
        assert issues[0].issue_type == "Closing keyword in fenced code block"

    def test_a_line_that_only_starts_with_the_fence_chars_does_not_close_it(self):
        """A closing fence line must hold nothing but the fence run and
        trailing whitespace. A line that merely starts with the same run
        (e.g. a fence marker immediately followed by other text) is still
        code to GitHub and must not end the block early (Copilot, PR #5371
        round 2)."""
        body = "```\n```not-a-closer\nFixes #42\n```\n"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_closer_longer_than_opener_still_closes_the_fence(self):
        """CommonMark 0.31.2 4.5: the closer must be the same character and
        AT LEAST as long as the opener, not exactly as long. A 3-backtick
        opener closes on a 4-backtick line, so a keyword after it is real,
        unfenced text and must be reported as a genuine closing keyword, not
        excused as still-fenced (Copilot, PR #5371 round 3)."""
        body = "```\nignore this\n````\nFixes #42\n"
        assert validate_closing_links(body, "main", "main") == []


class TestStackedPR:
    """Non-default base branch should produce WARNING when body has closing keywords."""

    def test_stacked_pr_warning(self):
        body = "Fixes #200\n"
        issues = validate_closing_links(body, base_branch="feature-base", default_branch="main")
        assert len(issues) == 1
        assert issues[0].severity == "WARNING"
        assert issues[0].issue_type == "Closing keyword on non-default base branch"
        assert "feature-base" in issues[0].message
        assert "main" in issues[0].message

    def test_stacked_pr_no_keyword_no_warning(self):
        body = "No closing keywords here.\n"
        issues = validate_closing_links(body, base_branch="feature-base", default_branch="main")
        assert issues == []

    def test_default_branch_no_warning(self):
        body = "Fixes #200\n"
        issues = validate_closing_links(body, base_branch="main", default_branch="main")
        assert issues == []

    def test_stacked_pr_code_span_gets_critical_and_warning(self):
        # Both the code span violation AND the non-default base apply
        body = "`Fixes #200`"
        issues = validate_closing_links(body, base_branch="stack", default_branch="main")
        severities = {i.severity for i in issues}
        assert "CRITICAL" in severities
        assert "WARNING" in severities


class TestBlockquote:
    """Blockquotes are prose, not code; closing keywords in them are honored."""

    def test_keyword_in_blockquote_is_valid(self):
        body = "> Fixes #99\n"
        assert validate_closing_links(body, "main", "main") == []


class TestEdgeCases:
    def test_empty_body(self):
        assert validate_closing_links("", "main", "main") == []

    def test_body_with_no_keywords(self):
        body = "This PR improves performance by 20%."
        assert validate_closing_links(body, "main", "main") == []

    def test_case_insensitive_keyword(self):
        body = "`fixes #42`"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"

    def test_cross_repo_ref_in_code_span(self):
        # Cross-repo refs are not closing keywords for this repo; still flag
        body = "`Fixes other/repo#42`"
        issues = validate_closing_links(body, "main", "main")
        assert len(issues) == 1
        assert issues[0].severity == "CRITICAL"


class TestMultilineCodeSpanNegativeControl:
    """A closing link inside a multiline code span must not count as real.

    CommonMark allows a line ending inside a code span; only a blank line ends
    it. Restricting the body to a single line left these unstripped, so an
    example was read as a genuine closing link and the gate passed on a pull
    request that closes nothing. Refs #3827.

    Asserted through validate_closing_links rather than the regex so the test
    fails if the stripping stops being consulted, not only if the pattern
    changes.
    """

    def test_multiline_single_backtick_span_does_not_satisfy_the_gate(self) -> None:
        body = "Some text\n\n`example\nFixes #123`\n"
        assert validate_closing_links(body, "main", "main") != []

    def test_multiline_double_backtick_span_does_not_satisfy_the_gate(self) -> None:
        body = "Some text\n\n``ex `tick`\nFixes #123``\n"
        assert validate_closing_links(body, "main", "main") != []

    def test_blank_line_ends_the_span_so_the_link_counts(self) -> None:
        """The inverse control: a blank line closes the span per CommonMark."""
        body = "`example\n\nFixes #123`\n"
        assert validate_closing_links(body, "main", "main") == []

    def test_a_real_closing_link_still_satisfies_the_gate(self) -> None:
        body = "This change is complete.\n\nFixes #123\n"
        assert validate_closing_links(body, "main", "main") == []
