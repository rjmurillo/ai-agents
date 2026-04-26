"""Tests for scripts.validation.pr_description module."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation.pr_description import (
    Issue,
    RepoInfo,
    _safe_label_for_markdown,
    _safe_label_for_output,
    _strip_informational_sections,
    extract_mentioned_files,
    fetch_pr_data,
    file_matches,
    get_repo_info,
    main,
    normalize_path,
    print_results,
    validate_pr_description,
)

# ---------------------------------------------------------------------------
# normalize_path
# ---------------------------------------------------------------------------


class TestNormalizePath:
    def test_strips_whitespace(self) -> None:
        assert normalize_path("  foo.py  ") == "foo.py"

    def test_converts_backslashes(self) -> None:
        assert normalize_path("src\\foo\\bar.py") == "src/foo/bar.py"

    def test_removes_leading_dot_slash(self) -> None:
        assert normalize_path("./scripts/foo.py") == "scripts/foo.py"

    def test_no_change_for_clean_path(self) -> None:
        assert normalize_path("scripts/foo.py") == "scripts/foo.py"

    def test_combined_normalization(self) -> None:
        assert normalize_path(" .\\src\\bar.py ") == "src/bar.py"

    def test_strips_markdown_bold_markers(self) -> None:
        assert normalize_path("**foo.yml") == "foo.yml"

    def test_strips_surrounding_bold_markers(self) -> None:
        assert normalize_path("**foo.yml**") == "foo.yml"

    def test_strips_backticks(self) -> None:
        assert normalize_path("`foo.yml") == "foo.yml"

    def test_strips_surrounding_backticks(self) -> None:
        assert normalize_path("`foo.yml`") == "foo.yml"


# ---------------------------------------------------------------------------
# file_matches
# ---------------------------------------------------------------------------


class TestFileMatches:
    def test_exact_match(self) -> None:
        assert file_matches("scripts/foo.py", "scripts/foo.py") is True

    def test_suffix_match(self) -> None:
        assert file_matches("path/to/foo.py", "foo.py") is True

    def test_no_match(self) -> None:
        assert file_matches("scripts/foo.py", "bar.py") is False

    def test_partial_name_no_match(self) -> None:
        assert file_matches("scripts/xfoo.py", "foo.py") is False

    def test_empty_strings(self) -> None:
        assert file_matches("", "") is True

    def test_glob_star_match(self) -> None:
        assert file_matches(".github/prompts/pr-quality-gate-qa.md",
                            ".github/prompts/pr-quality-gate-*.md") is True

    def test_glob_directory_star(self) -> None:
        assert file_matches(".claude/commands/pr-quality/analyst.md",
                            ".claude/commands/pr-quality/*.md") is True

    def test_glob_no_match(self) -> None:
        assert file_matches("scripts/foo.py",
                            "scripts/*.md") is False

    def test_glob_question_mark(self) -> None:
        assert file_matches("src/a.py", "src/?.py") is True


# ---------------------------------------------------------------------------
# extract_mentioned_files
# ---------------------------------------------------------------------------


class TestExtractMentionedFiles:
    def test_inline_code(self) -> None:
        desc = "Changed `scripts/foo.py` and `bar.ts`"
        result = extract_mentioned_files(desc)
        assert "scripts/foo.py" in result
        assert "bar.ts" in result

    def test_bold_text(self) -> None:
        desc = "Modified **config.yml**"
        result = extract_mentioned_files(desc)
        assert "config.yml" in result

    def test_list_items(self) -> None:
        desc = "- scripts/foo.ps1\n* src/bar.cs\n+ lib/baz.js"
        result = extract_mentioned_files(desc)
        assert "scripts/foo.ps1" in result
        assert "src/bar.cs" in result
        assert "lib/baz.js" in result

    def test_list_items_with_backtick_wrapped_paths(self) -> None:
        r"""Autonomous PR template wraps list-item file paths in backticks.

        Regression coverage for issue #1711: the file mention regex must
        extract paths from `- \`path/file.ext\`: description` just like it
        does from `- path/file.ext`.
        """
        desc = (
            "## Changes\n"
            "- `packages/ai-agents-cli/package.json`: Updated configuration\n"
            "- `scripts/foo.py`: Refactored entry point\n"
            "- `src/index.ts`: Fixed bug\n"
        )
        result = extract_mentioned_files(desc)
        assert "packages/ai-agents-cli/package.json" in result
        assert "scripts/foo.py" in result
        assert "src/index.ts" in result
        # Backticks must be fully stripped from the extracted paths.
        assert not any("`" in path for path in result)

    def test_markdown_links(self) -> None:
        desc = "See [config.json] for details"
        result = extract_mentioned_files(desc)
        assert "config.json" in result

    def test_deduplication(self) -> None:
        desc = "`foo.py` and `foo.py` again"
        result = extract_mentioned_files(desc)
        assert result.count("foo.py") == 1

    def test_empty_description(self) -> None:
        assert extract_mentioned_files("") == []

    def test_none_description(self) -> None:
        assert extract_mentioned_files("") == []

    def test_no_files_mentioned(self) -> None:
        desc = "This PR fixes a bug in the login flow."
        result = extract_mentioned_files(desc)
        assert result == []

    def test_path_normalization_applied(self) -> None:
        desc = "`./scripts/foo.py`"
        result = extract_mentioned_files(desc)
        assert "scripts/foo.py" in result

    def test_multiple_patterns_combined(self) -> None:
        desc = "`a.py` and **b.yml** and\n- c.ts"
        result = extract_mentioned_files(desc)
        assert len(result) == 3

    def test_bold_in_list_item_deduplicates(self) -> None:
        """Bold filenames in list items should not produce duplicates with bold markers."""
        desc = "- **workflow.yml**: Added skip job"
        result = extract_mentioned_files(desc)
        assert result == ["workflow.yml"]

    def test_command_in_backticks_not_treated_as_file(self) -> None:
        desc = "- [x] `uv run mypy scripts/homework_scanner.py` (clean)"
        result = extract_mentioned_files(desc)
        assert "uv run mypy scripts/homework_scanner.py" not in result

    def test_renovate_detected_package_files_ignored(self) -> None:
        desc = (
            "### Detected Package Files\n\n"
            " * `.github/workflows/pytest.yml` (github-actions)\n"
            " * `pyproject.toml` (pep621)\n\n"
            "---\n\n"
            "Changed `renovate.json` configuration."
        )
        result = extract_mentioned_files(desc)
        assert "renovate.json" in result
        assert ".github/workflows/pytest.yml" not in result
        assert "pyproject.toml" not in result

    def test_github_admonition_blockquotes_ignored(self) -> None:
        desc = (
            "Welcome to Renovate!\n\n"
            "> [!WARNING]\n"
            "> Please correct these dependency lookup failures.\n"
            ">\n"
            "> Files affected: `.github/workflows/codeql-analysis.yml`\n\n"
            "Updated `renovate.json`."
        )
        result = extract_mentioned_files(desc)
        assert "renovate.json" in result
        assert ".github/workflows/codeql-analysis.yml" not in result

    def test_details_blocks_ignored(self) -> None:
        desc = (
            "<details>\n"
            "<summary>chore(deps): update actions/cache</summary>\n\n"
            "  - Upgrade `actions/cache` to `abc123`\n"
            "  - Branch: `renovate/actions-cache-digest`\n\n"
            "</details>\n\n"
            "Updated `renovate.json`."
        )
        result = extract_mentioned_files(desc)
        assert "renovate.json" in result
        assert not any("actions/cache" in f for f in result)

    def test_test_plan_section_ignored(self) -> None:
        desc = (
            "## Summary\n"
            "Updated `skill.md` with new patterns.\n\n"
            "## Test plan\n"
            "- [ ] Skill validates against `.claude/skills/CLAUDE.md` conventions\n"
            "- [ ] No breaking changes\n"
        )
        result = extract_mentioned_files(desc)
        assert "skill.md" in result
        assert ".claude/skills/CLAUDE.md" not in result

    def test_design_decisions_section_ignored(self) -> None:
        """Issue #1780 repro: PR #1724 'Design Decisions' references a sibling
        file as a pattern source. The validator must not treat that as a
        change claim."""
        desc = (
            "## Summary\n"
            "Adds five new lifecycle hooks.\n\n"
            "## Design Decisions\n"
            "- **Existing patterns** - follows same structure as "
            "`invoke_skill_learning.py`\n"
            "- **Python-first** (ADR-042)\n"
        )
        result = extract_mentioned_files(desc)
        assert "invoke_skill_learning.py" not in result

    def test_related_section_ignored(self) -> None:
        desc = (
            "## Summary\n"
            "Refactor of `scripts/foo.py`.\n\n"
            "## Related\n"
            "- See `scripts/legacy.py` for the prior approach\n"
            "- ADR-008\n"
        )
        result = extract_mentioned_files(desc)
        assert "scripts/foo.py" in result
        assert "scripts/legacy.py" not in result

    def test_references_section_ignored(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## References\n- `b.py` documents the spec\n"
        )
        result = extract_mentioned_files(desc)
        assert "a.py" in result
        assert "b.py" not in result

    def test_see_also_section_ignored(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## See Also\n- `b.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "b.py" not in result

    def test_notes_section_ignored(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## Notes\nInspired by approach in `b.py`.\n"
        )
        result = extract_mentioned_files(desc)
        assert "b.py" not in result

    def test_background_section_ignored(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## Background\nBuilds on work in `b.py`.\n"
        )
        result = extract_mentioned_files(desc)
        assert "b.py" not in result

    def test_inspired_by_section_ignored(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## Inspired By\n- `b.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "b.py" not in result

    def test_pattern_from_section_ignored(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## Pattern From\n- `b.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "b.py" not in result

    def test_contextual_section_case_insensitive(self) -> None:
        desc = (
            "## Summary\nChanged `a.py`.\n\n"
            "## DESIGN DECISIONS\n- See `b.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "b.py" not in result

    def test_contextual_section_terminates_at_next_h2(self) -> None:
        """Stripping must stop at the next `##` heading so files mentioned in
        a later section (e.g. ## Changes) are still extracted."""
        desc = (
            "## Design Decisions\n"
            "- See `pattern.py`\n\n"
            "## Changes\n"
            "- `real_change.py`: the actual edit\n"
        )
        result = extract_mentioned_files(desc)
        assert "pattern.py" not in result
        assert "real_change.py" in result

    def test_notes_with_trailing_text_not_stripped(self) -> None:
        """Heading must be the WHOLE `## ...` line. `## Notes on iteration 2`
        is a section title that may contain real change claims; treating
        every prefix-match as informational silently drops real claims.
        Codex P1 finding from PR #1781 review."""
        desc = (
            "## Summary\n"
            "Refactor.\n\n"
            "## Notes on iteration 2\n"
            "- Added `new_module.py`\n"
            "- Removed `legacy.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "new_module.py" in result
        assert "legacy.py" in result

    def test_design_decisions_with_trailing_text_not_stripped(self) -> None:
        """Same protection for `## Design Decisions for X` style headings."""
        desc = (
            "## Summary\n"
            "Edit.\n\n"
            "## Design Decisions for the cache layer\n"
            "- `cache.py` rewritten\n"
        )
        result = extract_mentioned_files(desc)
        assert "cache.py" in result

    def test_bare_heading_with_trailing_whitespace_still_strips(self) -> None:
        """Trailing whitespace on a bare heading line must still strip."""
        desc = (
            "## Summary\n"
            "Changed `real.py`.\n\n"
            "## Design Decisions   \n"
            "- See `pattern.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "pattern.py" not in result

    def test_h1_terminates_contextual_section_strip(self) -> None:
        """Per CommonMark, an H2 section ends at the next heading of equal-
        or-higher level. An H1 (`# ...`) following `## Design Decisions`
        must terminate the strip; otherwise content under the H1 is
        silently dropped. Gemini bot finding on PR #1781."""
        desc = (
            "## Design Decisions\n"
            "- See `pattern.py`\n\n"
            "# Major Section Reset\n"
            "- Modified `real.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "pattern.py" not in result
        assert "real.py" in result

    def test_h3_subheading_inside_contextual_section_is_stripped(self) -> None:
        """A `### Sub-heading` inside a stripped `## Design Decisions` block
        must NOT terminate the strip. Without `(?!#)` in the lookahead, the
        regex matches `###` (since it starts with `##`) and the H3 body leaks
        as phantom claims. Self-finding from /review iteration."""
        desc = (
            "## Summary\n"
            "Changed `real.py`.\n\n"
            "## Design Decisions\n"
            "- Pattern from `pattern.py`\n\n"
            "### Trade-offs\n"
            "- Considered `alt.py`\n"
            "- Rejected because slow\n\n"
            "## Changes\n"
            "- `real.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "real.py" in result
        assert "pattern.py" not in result
        assert "alt.py" not in result

    def test_deeply_nested_subheadings_inside_contextual_section_stripped(
        self,
    ) -> None:
        """H4 and H5 sub-headings inside a contextual section must also stay
        within the strip range (only `^##` exactly terminates)."""
        desc = (
            "## Notes\n"
            "- ref `a.py`\n"
            "#### Deep\n"
            "- `b.py`\n"
            "##### Deeper\n"
            "- `c.py`\n"
            "## Changes\n"
            "- `real.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert result == ["real.py"]

    def test_h3_design_decisions_not_stripped(self) -> None:
        """Only `##` (h2) sections strip. `### Design Decisions` stays so we
        do not silently swallow file claims under nested headings."""
        desc = (
            "## Summary\n"
            "### Design Decisions\n"
            "- Modified `kept.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "kept.py" in result

    def test_fenced_contextual_heading_does_not_overstrip(self) -> None:
        """A `## Design Decisions` heading INSIDE a fenced code block must not
        anchor the contextual-section regex. Without code-block masking, the
        strip would consume across the fence boundary and expose phantom
        change claims from inside the sample."""
        desc = (
            "## Summary\n"
            "Changed `summary.py`.\n\n"
            "```markdown\n"
            "example template snippet:\n"
            "## Design Decisions\n"
            "- `inside_fence_phantom.py`\n"
            "```\n\n"
            "## Changes\n"
            "- `actual.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "summary.py" in result
        assert "actual.py" in result
        # Filenames inside fenced samples are not change claims.
        assert "inside_fence_phantom.py" not in result

    def test_fenced_filename_under_contextual_section_masked(self) -> None:
        """When a real `## Design Decisions` section contains a fenced sample
        with a filename, neither the sample filename nor the surrounding
        contextual references leak into extraction."""
        desc = (
            "## Summary\n"
            "Changed `real.py`.\n\n"
            "## Design Decisions\n"
            "Pattern from earlier work:\n\n"
            "```python\n"
            "# example using template.py\n"
            "import os\n"
            "```\n"
            "Adopted from `pattern.py`.\n"
        )
        result = extract_mentioned_files(desc)
        assert "real.py" in result
        assert "pattern.py" not in result
        assert "template.py" not in result

    def test_tilde_fenced_block_masked(self) -> None:
        """CommonMark allows `~~~` as a fence delimiter. AI-generated PR
        descriptions sometimes use it. The mask must cover both styles or
        a sample heading inside `~~~` over-strips the surrounding document."""
        desc = (
            "## Summary\n"
            "Changed `real.py`.\n\n"
            "~~~markdown\n"
            "## Design Decisions\n"
            "- `phantom.py`\n\n"
            "## Changes\n"
            "- `fakelink_inside_fence.py`\n"
            "~~~\n\n"
            "## Changes\n"
            "- `actual.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "real.py" in result
        assert "actual.py" in result
        assert "phantom.py" not in result
        assert "fakelink_inside_fence.py" not in result

    def test_tilde_fence_unanchored_strikethrough_does_not_mask_real_h2(
        self,
    ) -> None:
        """Mid-prose `~~~strike~~~` must NOT mask between two such tokens.
        Without the start-of-line anchor, the regex would match
        `~~~strike~~~ ... ~~~something~~~` and silently swallow any
        contextual heading appearing between them."""
        desc = (
            "## Summary\n"
            "Text with ~~~strike~~~ and another ~~~thing~~~ inline.\n\n"
            "## Test Plan\n"
            "- ref `validation_target.md`\n"
        )
        # Test Plan section MUST still be stripped (validation target is
        # informational). If the unanchored tilde regex matched the inline
        # `~~~strike~~~ ... ~~~thing~~~` and masked across the boundary,
        # the `## Test Plan` heading would be inside a CODE_BLOCK token and
        # would NOT be stripped, causing `validation_target.md` to leak.
        result = extract_mentioned_files(desc)
        assert "validation_target.md" not in result

    def test_html_pre_block_masked(self) -> None:
        """PR templates and bot-generated descriptions sometimes embed `<pre>`
        blocks. The mask must cover them or a sample heading inside `<pre>`
        over-strips the surrounding document."""
        desc = (
            "## Summary\n"
            "Changed `real.py`.\n\n"
            "<pre lang=\"markdown\">\n"
            "## Design Decisions\n"
            "sample\n"
            "## Changes\n"
            "- `fakelink_inside_pre.py`\n"
            "</pre>\n\n"
            "## Changes\n"
            "- `actual.py`\n"
        )
        result = extract_mentioned_files(desc)
        assert "real.py" in result
        assert "actual.py" in result
        assert "fakelink_inside_pre.py" not in result


# ---------------------------------------------------------------------------
# _strip_informational_sections
# ---------------------------------------------------------------------------


class TestStripInformationalSections:
    def test_strips_details_blocks(self) -> None:
        text = "before\n<details>\nhidden\n</details>\nafter"
        result = _strip_informational_sections(text)
        assert "hidden" not in result
        assert "before" in result
        assert "after" in result

    def test_strips_detected_package_files_section(self) -> None:
        text = (
            "Intro\n\n"
            "### Detected Package Files\n\n"
            " * `foo.yml`\n"
            " * `bar.yml`\n\n"
            "---\n\n"
            "Footer"
        )
        result = _strip_informational_sections(text)
        assert "foo.yml" not in result
        assert "Footer" in result

    def test_strips_github_admonition_blockquotes(self) -> None:
        text = (
            "Some intro text.\n\n"
            "> [!WARNING]\n"
            "> Please correct these dependency lookup failures.\n"
            ">\n"
            "> -   `Could not determine new digest`\n"
            ">\n"
            "> Files affected: `.github/workflows/codeql-analysis.yml`\n\n"
            "Footer text."
        )
        result = _strip_informational_sections(text)
        assert "codeql-analysis.yml" not in result
        assert "Some intro text" in result
        assert "Footer text" in result

    def test_strips_test_plan_sections(self) -> None:
        text = (
            "## Summary\n"
            "Changed `foo.py`.\n\n"
            "## Test plan\n"
            "- [ ] Validates against `.claude/skills/CLAUDE.md` conventions\n"
            "- [ ] Tests pass locally\n"
        )
        result = _strip_informational_sections(text)
        assert ".claude/skills/CLAUDE.md" not in result
        assert "foo.py" in result

    def test_strips_design_decisions_section(self) -> None:
        text = (
            "## Summary\nChanged `foo.py`.\n\n"
            "## Design Decisions\n- follows `pattern.py`\n"
        )
        result = _strip_informational_sections(text)
        assert "pattern.py" not in result
        assert "foo.py" in result

    def test_strips_related_section(self) -> None:
        text = (
            "## Summary\nChanged `foo.py`.\n\n"
            "## Related\n- `prior.py`\n"
        )
        result = _strip_informational_sections(text)
        assert "prior.py" not in result
        assert "foo.py" in result

    def test_strips_test_plan_with_next_heading(self) -> None:
        """Test plan strip terminates at the next h2 heading. Uses `## Changes`
        (not `## Notes`, which is now in the contextual allowlist) as the
        terminating heading."""
        text = (
            "## Summary\n"
            "Changed `foo.py`.\n\n"
            "## Test Plan\n"
            "- Check `conventions.md` compliance\n\n"
            "## Changes\n"
            "- Updated `bar.py`."
        )
        result = _strip_informational_sections(text)
        assert "conventions.md" not in result
        assert "foo.py" in result
        assert "bar.py" in result

    def test_preserves_non_informational_content(self) -> None:
        text = "Changed `scripts/foo.py` and **bar.yml**"
        result = _strip_informational_sections(text)
        assert result == text

    def test_masks_fenced_code_blocks_before_section_strip(self) -> None:
        """Fenced code blocks must be masked before contextual-section
        stripping so a sample heading inside a fence does not anchor the
        regex and over-strip across the real document structure."""
        text = (
            "## Summary\nChanged `real.py`.\n\n"
            "```\n## Design Decisions\nphantom\n```\n\n"
            "## Changes\n- `actual.py`\n"
        )
        result = _strip_informational_sections(text)
        # The `## Changes` heading must survive intact.
        assert "## Changes" in result
        assert "actual.py" in result
        # The fenced sample is masked, so its `## Design Decisions` heading
        # cannot anchor the contextual-section regex.
        assert "phantom" not in result


# ---------------------------------------------------------------------------
# validate_pr_description
# ---------------------------------------------------------------------------


class TestValidatePRDescription:
    def test_no_issues_when_match(self) -> None:
        issues = validate_pr_description(
            pr_files=["scripts/foo.py"],
            mentioned_files=["scripts/foo.py"],
        )
        assert len(issues) == 0

    def test_critical_when_mentioned_but_not_in_diff(self) -> None:
        issues = validate_pr_description(
            pr_files=["scripts/foo.py"],
            mentioned_files=["scripts/bar.py"],
        )
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical) == 1
        assert critical[0].file == "scripts/bar.py"

    def test_warning_when_significant_file_not_mentioned(self) -> None:
        issues = validate_pr_description(
            pr_files=[".github/workflows/ci.yml"],
            mentioned_files=[],
        )
        warnings = [i for i in issues if i.severity == "WARNING"]
        assert len(warnings) == 1
        assert warnings[0].file == ".github/workflows/ci.yml"

    def test_no_warning_for_non_significant_extension(self) -> None:
        issues = validate_pr_description(
            pr_files=["scripts/readme.txt"],
            mentioned_files=[],
        )
        assert len(issues) == 0

    def test_no_warning_for_non_significant_directory(self) -> None:
        issues = validate_pr_description(
            pr_files=["docs/guide.py"],
            mentioned_files=[],
        )
        assert len(issues) == 0

    def test_suffix_match_prevents_critical(self) -> None:
        issues = validate_pr_description(
            pr_files=["path/to/foo.py"],
            mentioned_files=["foo.py"],
        )
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical) == 0

    def test_empty_files_lists(self) -> None:
        issues = validate_pr_description(pr_files=[], mentioned_files=[])
        assert len(issues) == 0

    def test_glob_pattern_prevents_critical(self) -> None:
        issues = validate_pr_description(
            pr_files=[
                ".github/prompts/pr-quality-gate-analyst.md",
                ".github/prompts/pr-quality-gate-qa.md",
            ],
            mentioned_files=[".github/prompts/pr-quality-gate-*.md"],
        )
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical) == 0

    def test_mixed_critical_and_warning(self) -> None:
        issues = validate_pr_description(
            pr_files=["scripts/changed.py"],
            mentioned_files=["ghost.py"],
        )
        critical = [i for i in issues if i.severity == "CRITICAL"]
        warnings = [i for i in issues if i.severity == "WARNING"]
        assert len(critical) == 1
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# print_results
# ---------------------------------------------------------------------------


class TestPrintResults:
    def test_no_issues_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = print_results([], ci=False)
        assert code == 0
        assert "no mismatches found" in capsys.readouterr().out

    def test_warnings_only_returns_zero(self) -> None:
        issues = [
            Issue("WARNING", "Not mentioned", "f.py", "msg"),
        ]
        code = print_results(issues, ci=True)
        assert code == 0

    def test_critical_in_ci_returns_one(self) -> None:
        issues = [
            Issue("CRITICAL", "Phantom file", "f.py", "msg"),
        ]
        code = print_results(issues, ci=True)
        assert code == 1

    def test_critical_without_ci_returns_zero(self) -> None:
        issues = [
            Issue("CRITICAL", "Phantom file", "f.py", "msg"),
        ]
        code = print_results(issues, ci=False)
        assert code == 0

    def test_unrecognized_severity_rejected_at_construction(self) -> None:
        """Issue.severity is a closed Literal["CRITICAL","WARNING"]. A typo
        like "critical" or "INFO" must raise at construction time, not
        silently slip past the CRITICAL gate at validate_pr_description."""
        with pytest.raises(ValueError, match="must be one of"):
            Issue("INFO", "Note", "f.py", "msg")
        with pytest.raises(ValueError, match="must be one of"):
            Issue("critical", "Note", "f.py", "msg")  # case matters


# ---------------------------------------------------------------------------
# get_repo_info
# ---------------------------------------------------------------------------


class TestGetRepoInfo:
    @patch("scripts.validation.pr_description.subprocess.run")
    def test_https_url(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/myorg/myrepo.git\n",
        )
        info = get_repo_info()
        assert info == RepoInfo(owner="myorg", repo="myrepo")

    @patch("scripts.validation.pr_description.subprocess.run")
    def test_ssh_url(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="git@github.com:myorg/myrepo.git\n",
        )
        info = get_repo_info()
        assert info == RepoInfo(owner="myorg", repo="myrepo")

    @patch("scripts.validation.pr_description.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        with pytest.raises(RuntimeError, match="Could not determine"):
            get_repo_info()

    @patch("scripts.validation.pr_description.subprocess.run")
    def test_unparseable_url_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://gitlab.com/foo/bar\n"
        )
        with pytest.raises(RuntimeError, match="Could not parse"):
            get_repo_info()

    @patch(
        "scripts.validation.pr_description.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_git_not_found_raises(self, mock_run: MagicMock) -> None:
        with pytest.raises(RuntimeError, match="Could not determine"):
            get_repo_info()


# ---------------------------------------------------------------------------
# fetch_pr_data
# ---------------------------------------------------------------------------


class TestFetchPRData:
    @patch("scripts.validation.pr_description.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        pr_json = json.dumps(
            {"title": "Test", "body": "desc", "files": [{"path": "a.py"}]}
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=pr_json)
        data = fetch_pr_data(1, "owner", "repo")
        assert data["title"] == "Test"

    @patch("scripts.validation.pr_description.subprocess.run")
    def test_requests_labels_field(self, mock_run: MagicMock) -> None:
        """Bypass-label support requires labels in the gh JSON request."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"title": "T", "files": []})
        )
        fetch_pr_data(1, "owner", "repo")
        args = mock_run.call_args[0][0]
        json_idx = args.index("--json")
        assert "labels" in args[json_idx + 1].split(",")

    @patch("scripts.validation.pr_description.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            fetch_pr_data(1, "owner", "repo")

    @patch(
        "scripts.validation.pr_description.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_gh_not_found_raises(self, mock_run: MagicMock) -> None:
        with pytest.raises(RuntimeError, match="gh CLI not found"):
            fetch_pr_data(1, "owner", "repo")

    @patch(
        "scripts.validation.pr_description.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
    )
    def test_timeout_raises(self, mock_run: MagicMock) -> None:
        with pytest.raises(RuntimeError, match="Timed out"):
            fetch_pr_data(1, "owner", "repo")


# ---------------------------------------------------------------------------
# main (integration-style)
# ---------------------------------------------------------------------------


class TestMain:
    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_clean_pr_returns_zero(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "Test",
            "body": "Changed `foo.py`",
            "files": [{"path": "foo.py"}],
        }
        code = main(["--pr-number", "1"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_phantom_file_ci_returns_one(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "Test",
            "body": "Changed `ghost.py`",
            "files": [{"path": "foo.py"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 1

    @patch("scripts.validation.pr_description.fetch_pr_data")
    def test_owner_repo_from_args(
        self, mock_fetch: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        mock_fetch.return_value = {
            "title": "T",
            "body": "",
            "files": [],
        }
        code = main(["--pr-number", "1", "--owner", "org", "--repo", "proj"])
        assert code == 0
        mock_fetch.assert_called_once_with(1, "org", "proj")

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_owner_provided_repo_resolved_from_git(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`--owner` set, `--repo` omitted: git remote fills repo only."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("REPO_NAME", raising=False)
        monkeypatch.delenv("REPO_OWNER", raising=False)
        mock_repo.return_value = RepoInfo(owner="git_owner", repo="git_repo")
        mock_fetch.return_value = {"title": "T", "body": "", "files": []}
        code = main(["--pr-number", "1", "--owner", "cli_owner"])
        assert code == 0
        mock_fetch.assert_called_once_with(1, "cli_owner", "git_repo")

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_repo_provided_owner_resolved_from_git(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`--repo` set, `--owner` omitted: git remote fills owner only."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("REPO_NAME", raising=False)
        monkeypatch.delenv("REPO_OWNER", raising=False)
        mock_repo.return_value = RepoInfo(owner="git_owner", repo="git_repo")
        mock_fetch.return_value = {"title": "T", "body": "", "files": []}
        code = main(["--pr-number", "1", "--repo", "cli_repo"])
        assert code == 0
        mock_fetch.assert_called_once_with(1, "git_owner", "cli_repo")

    @patch(
        "scripts.validation.pr_description.get_repo_info",
        side_effect=RuntimeError("no git"),
    )
    def test_repo_info_failure_returns_two(self, mock_repo: MagicMock) -> None:
        code = main(["--pr-number", "1"])
        assert code == 2

    @patch(
        "scripts.validation.pr_description.fetch_pr_data",
        side_effect=RuntimeError("API down"),
    )
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_fetch_failure_returns_two(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        code = main(["--pr-number", "1"])
        assert code == 2

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_null_body_handled(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": None,
            "files": [{"path": "foo.py"}],
        }
        code = main(["--pr-number", "1"])
        assert code == 0


# ---------------------------------------------------------------------------
# Bypass label
# ---------------------------------------------------------------------------


class TestBypassLabel:
    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_present_returns_zero_on_critical(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
    ) -> None:
        """CRITICAL + bypass label → exit 0 in CI mode."""
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_absent_still_blocks_critical(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "some-other-label"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 1

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_custom_bypass_label_honored(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "skip-pr-desc"}],
        }
        code = main(["--pr-number", "1", "--ci", "--bypass-label", "skip-pr-desc"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_does_not_affect_clean_pr(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
    ) -> None:
        """When there are no CRITICAL issues, the bypass path is not taken."""
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `foo.py`",
            "files": [{"path": "foo.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_missing_labels_field_does_not_crash(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
    ) -> None:
        """Old gh responses without labels must still validate cleanly."""
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 1

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_ignored_outside_ci(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without --ci, CRITICAL never blocks regardless of label state."""
        monkeypatch.delenv("CI", raising=False)
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [],
        }
        code = main(["--pr-number", "1"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_case_insensitive(
        self, mock_repo: MagicMock, mock_fetch: MagicMock,
    ) -> None:
        """GitHub label names render case-insensitively. A maintainer who
        creates the label with different casing must still get the bypass."""
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "Description-Validation-Bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_emits_step_summary_audit_record(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When GITHUB_STEP_SUMMARY is set, bypass writes a structured marker
        so audit tooling can detect bypass-label use without parsing stdout."""
        summary = tmp_path / "summary.md"
        summary.write_text("")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0
        body = summary.read_text()
        assert "PR Description Validation Bypass" in body
        assert "DESCRIPTION-VALIDATION-BYPASS" in body
        assert "ghost.py" in body

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_no_bypass_audit_when_no_summary_env(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Local runs (no GITHUB_STEP_SUMMARY) must not crash and must
        not require a writable audit path."""
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_emits_github_output_signal(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bypass must signal the workflow via GITHUB_OUTPUT so the report
        step can render BYPASSED instead of a clean PASS in the PR comment.
        Codex P2 finding from PR #1781 review."""
        output = tmp_path / "outputs.txt"
        output.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py` and `phantom.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0
        body = output.read_text()
        assert "bypass_used=true" in body
        assert "bypass_label=description-validation-bypass" in body
        assert "bypass_count=2" in body

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_clean_pass_does_not_emit_bypass_output(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A clean PASS must NOT write any bypass_* keys to GITHUB_OUTPUT;
        otherwise the report would falsely flag every clean PR as bypassed."""
        output = tmp_path / "outputs.txt"
        output.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `foo.py`",
            "files": [{"path": "foo.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0
        body = output.read_text()
        assert "bypass_used" not in body
        assert "bypass_label" not in body

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_audit_swallows_summary_oserror(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A filesystem failure on GITHUB_STEP_SUMMARY write must NOT block
        the bypass return path. Defensive coverage for the audit emitter."""
        # Point GITHUB_STEP_SUMMARY at a directory; open(..., 'a') raises
        # IsADirectoryError (an OSError subclass). The bypass must still
        # exit 0 and the GITHUB_OUTPUT signal must still be emitted.
        bad_summary = tmp_path / "summary_dir"
        bad_summary.mkdir()
        good_output = tmp_path / "outputs.txt"
        good_output.write_text("")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(bad_summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(good_output))
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0
        # Output signal still landed despite summary failure.
        assert "bypass_used=true" in good_output.read_text()

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_audit_swallows_output_oserror(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A filesystem failure on GITHUB_OUTPUT write must NOT block the
        bypass return path. Failure must log to stderr (not silently
        swallow)."""
        bad_output = tmp_path / "output_dir"
        bad_output.mkdir()
        monkeypatch.setenv("GITHUB_OUTPUT", str(bad_output))
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0
        assert "WARNING: failed to write bypass audit" in capsys.readouterr().err

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_with_newline_does_not_inject_output_keys(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CWE-117 / CVE-2023-32700 class: a bypass label containing `\\n`
        could inject arbitrary GITHUB_OUTPUT keys (e.g.,
        `bypass\\nvalidation_result=PASS`). The sanitizer must replace
        newlines so only the intended bypass_used/label/count keys are
        emitted."""
        output = tmp_path / "outputs.txt"
        output.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        # Note: argparse/env doesn't easily allow a real newline; the
        # sanitizer must be applied unconditionally even if a future
        # caller passes one. We invoke the helper directly:
        from scripts.validation.pr_description import _write_step_output
        _write_step_output(str(output), "bypass\nvalidation_result=PASS", 1)
        body = output.read_text()
        assert "bypass_used=true" in body
        # Newline replaced; injection prevented.
        assert "\nvalidation_result=PASS" not in body
        assert "bypass_label=bypass_validation_result_PASS" in body

    def test_safe_label_for_output_replaces_dangerous_chars(self) -> None:
        assert _safe_label_for_output("a\nb") == "a_b"
        assert _safe_label_for_output("a\rb") == "a_b"
        assert _safe_label_for_output("a=b") == "a_b"
        assert _safe_label_for_output("clean-label") == "clean-label"

    def test_safe_label_for_output_replaces_all_control_chars(self) -> None:
        """Defense-in-depth: every ASCII control char (NUL through US plus
        DEL) must be replaced, not only the GHA line delimiters. Prevents
        future runner versions or heredoc parsers from being abused."""
        assert _safe_label_for_output("a\x00b") == "a_b"  # NUL
        assert _safe_label_for_output("a\x0bb") == "a_b"  # VT
        assert _safe_label_for_output("a\x0cb") == "a_b"  # FF
        assert _safe_label_for_output("a\x1bb") == "a_b"  # ESC
        assert _safe_label_for_output("a\x7fb") == "a_b"  # DEL
        assert _safe_label_for_output("a\tb") == "a_b"  # TAB also <0x20

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_label_sanitization_logs_warning_when_mutated(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When a sanitizer changes its input, stderr must record the
        mutation so auditors grepping for the original label name know
        why the value differs."""
        output = tmp_path / "outputs.txt"
        output.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "weird=label"}],
        }
        code = main(
            ["--pr-number", "1", "--ci", "--bypass-label", "weird=label"]
        )
        assert code == 0
        err = capsys.readouterr().err
        assert "sanitized" in err
        assert "weird=label" in err
        assert "weird_label" in err

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_clean_label_does_not_log_sanitization_warning(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No false-positive warning when label needed no sanitization."""
        output = tmp_path / "outputs.txt"
        output.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "description-validation-bypass"}],
        }
        code = main(["--pr-number", "1", "--ci"])
        assert code == 0
        assert "sanitized" not in capsys.readouterr().err

    def test_safe_label_for_markdown_replaces_backticks(self) -> None:
        assert _safe_label_for_markdown("a`b") == "a'b"
        assert _safe_label_for_markdown("clean") == "clean"

    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_bypass_label_with_backtick_does_not_break_markdown(
        self,
        mock_repo: MagicMock,
        mock_fetch: MagicMock,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A label containing a backtick must not close the inline code
        span in the audit summary, which would defeat the
        `<!-- DESCRIPTION-VALIDATION-BYPASS -->` parse contract."""
        summary = tmp_path / "summary.md"
        summary.write_text("")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_fetch.return_value = {
            "title": "T",
            "body": "Changed `ghost.py`",
            "files": [{"path": "real.py"}],
            "labels": [{"name": "weird`label"}],
        }
        code = main(
            ["--pr-number", "1", "--ci", "--bypass-label", "weird`label"]
        )
        assert code == 0
        body = summary.read_text()
        # Backtick replaced with single quote in the rendered label.
        assert "`weird'label`" in body
        # Audit marker still intact.
        assert "<!-- DESCRIPTION-VALIDATION-BYPASS -->" in body
