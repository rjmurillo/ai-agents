"""Markdown and prose validation tests for pre-PR checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch


class TestValidateMarkdownLint:
    """Markdown linting checks branch changes without masking unknown scope."""

    def test_returns_true_when_branch_has_no_markdown(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=[],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_not_called()

    def test_lints_changed_markdown_only(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=["README.md", "docs/guide.md"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2", "--fix", "README.md", "docs/guide.md"],
            cwd=tmp_path,
        )


    def test_skip_autofix_runs_check_only(
        self,
        tmp_path: Path,
        monkeypatch: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        monkeypatch.setenv("SKIP_AUTOFIX", "1")
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=["README.md"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2", "README.md"],
            cwd=tmp_path,
        )

    def test_falls_back_to_full_repo_when_scope_is_unknown(
        self, tmp_path: Path
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=None,
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (1, "", "markdownlint failed")
                    assert validate_markdown_lint(tmp_path) is False

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2", "--fix", "**/*.md"],
            cwd=tmp_path,
        )


class TestValidateDashProhibition:
    """Tests for the branch-wide em/en-dash check."""

    def test_returns_true_when_no_base_ref_resolves(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        # tmp_path is not a git repo; no ref will resolve.
        assert validate_dash_prohibition(tmp_path) is True

    def test_returns_true_for_clean_branch(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "README.md\n", ""),  # git diff
                (0, "clean content\n", ""),  # git show
            ]
            assert validate_dash_prohibition(tmp_path) is True

    def test_returns_false_on_em_dash(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        # _find_dash_violations now reads HEAD content via `git show`
        # rather than the working tree. Mock the two subprocess calls
        # in order: (1) git diff returns the file list, (2) git show
        # returns the file content as if from HEAD.
        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "doc.md\n", ""),  # git diff
                (0, f"prose with {chr(0x2014)} em-dash\n", ""),  # git show
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_returns_false_on_en_dash(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "range.md\n", ""),
                (0, f"range 1{chr(0x2013)}10\n", ""),
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_skips_vendored_paths(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        vendored = tmp_path / "node_modules" / "pkg" / "README.md"
        vendored.parent.mkdir(parents=True)
        vendored.write_text(f"upstream prose with {chr(0x2014)} dash\n", encoding="utf-8")
        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "node_modules/pkg/README.md\n", "")
            assert validate_dash_prohibition(tmp_path) is True

    def test_skips_test_fixtures_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        fixture = tmp_path / "tests" / "hooks" / "fixtures" / "dash_violations.md"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(f"intentional {chr(0x2014)}\n", encoding="utf-8")
        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "tests/hooks/fixtures/dash_violations.md\n", "")
            assert validate_dash_prohibition(tmp_path) is True

    def test_includes_github_instructions_tree(self, tmp_path: Path) -> None:
        """REQ-006-AC4: .github/instructions/ is NOT excluded."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, ".github/instructions/universal.instructions.md\n", ""),
                (0, f"prose {chr(0x2014)} dash\n", ""),
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_returns_true_when_git_diff_fails(self, tmp_path: Path) -> None:
        """Fail open on git subprocess failure (do not block on infra issues)."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (128, "", "fatal: bad revision")
            assert validate_dash_prohibition(tmp_path) is True

    def test_reads_head_content_not_working_tree(self, tmp_path: Path) -> None:
        """`_find_dash_violations` reads HEAD via `git show`, not the working tree.

        Working-tree edit could differ from committed content. The branch-wide
        scan must reflect what is committed (HEAD), since the diff scope
        comes from `git diff base...HEAD`.
        """
        from scripts.validation.pre_pr import validate_dash_prohibition

        # Working tree clean, but HEAD content (mocked) has em-dash:
        # the function MUST flag it.
        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "doc.md\n", ""),
                # HEAD content has dash; working tree (clean) does not.
                (0, f"committed em-dash {chr(0x2014)} here\n", ""),
            ]
            # No file at tmp_path/doc.md (working tree). Function should
            # still detect the violation because it reads HEAD content.
            assert validate_dash_prohibition(tmp_path) is False
