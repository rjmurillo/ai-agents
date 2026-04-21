"""Tests for scripts.validation.pr_description module."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation.pr_description import (
    Issue,
    RepoInfo,
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

    def test_strips_test_plan_with_next_heading(self) -> None:
        text = (
            "## Summary\n"
            "Changed `foo.py`.\n\n"
            "## Test Plan\n"
            "- Check `conventions.md` compliance\n\n"
            "## Notes\n"
            "Some notes here."
        )
        result = _strip_informational_sections(text)
        assert "conventions.md" not in result
        assert "foo.py" in result
        assert "Some notes here" in result

    def test_preserves_non_informational_content(self) -> None:
        text = "Changed `scripts/foo.py` and **bar.yml**"
        result = _strip_informational_sections(text)
        assert result == text


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
