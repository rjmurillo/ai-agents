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
