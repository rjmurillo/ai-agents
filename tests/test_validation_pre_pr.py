"""Tests for scripts.validation.pre_pr module.

Validates the pre-PR validation runner including individual validations,
result tracking, and CLI behavior. External tool calls are mocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import call, patch

import pytest

from scripts.validation.pre_pr import (
    ValidationState,
    _find_latest_session_log,
    _parse_yaml_frontmatter,
    _run_subprocess,
    build_parser,
    main,
    run_validation,
    validate_design_review_frontmatter,
    validate_review_marker,
    validate_session_end,
    validate_workflow_yaml,
)

# ---------------------------------------------------------------------------
# _find_latest_session_log
# ---------------------------------------------------------------------------


class TestFindLatestSessionLog:
    """Tests for session log discovery."""

    def test_returns_none_when_no_directory(self, tmp_path: Path) -> None:
        assert _find_latest_session_log(tmp_path) is None

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        assert _find_latest_session_log(tmp_path) is None

    def test_finds_latest_log(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("old", encoding="utf-8")
        (sessions / "2025-12-02-session-1.md").write_text("new", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-02-session-1.md"

    def test_ignores_non_matching_files(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "README.md").write_text("not a log", encoding="utf-8")
        (sessions / "2025-12-01-session-1.md").write_text("log", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-01-session-1.md"


# ---------------------------------------------------------------------------
# _run_subprocess
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    """Tests for subprocess runner."""

    def test_successful_command(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["echo", "hello"])
        assert exit_code == 0
        assert "hello" in stdout

    def test_command_not_found(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(
            ["nonexistent_command_xyz_123"]
        )
        assert exit_code == -1
        assert "not found" in stderr.lower() or "Command not found" in stderr


# ---------------------------------------------------------------------------
# ValidationState / run_validation
# ---------------------------------------------------------------------------


class TestRunValidation:
    """Tests for validation runner and state tracking."""

    def test_passing_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: True)
        assert result is True
        assert state.total == 1
        assert state.passed == 1
        assert state.failed == 0

    def test_failing_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: False)
        assert result is False
        assert state.total == 1
        assert state.passed == 0
        assert state.failed == 1

    def test_skipped_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: True, skip=True)
        assert result is True
        assert state.total == 1
        assert state.skipped == 1
        assert state.passed == 0

    def test_exception_counts_as_failure(self) -> None:
        def raise_error() -> bool:
            raise RuntimeError("boom")

        state = ValidationState()
        result = run_validation("Test Check", state, raise_error)
        assert result is False
        assert state.failed == 1

    def test_missing_script_skip_does_not_fail(self) -> None:
        """MissingScriptSkip should be reported as SKIP, not FAIL.

        Regression guard for issue #1850: pre_pr.py must not produce FAIL
        lines for PowerShell scripts expunged per ADR-042.
        """
        from scripts.validation.pre_pr import MissingScriptSkip

        def raise_skip() -> bool:
            raise MissingScriptSkip("Some-Validator.ps1 not present")

        state = ValidationState()
        result = run_validation("Test Check", state, raise_skip)
        assert result is True  # SKIP must not block the gate
        assert state.skipped == 1
        assert state.failed == 0
        assert state.passed == 0
        assert state.results[0].status == "SKIP"

    def test_records_duration(self) -> None:
        state = ValidationState()
        run_validation("Test Check", state, lambda: True)
        assert state.results[0].duration >= 0

    def test_multiple_validations(self) -> None:
        state = ValidationState()
        run_validation("Check 1", state, lambda: True)
        run_validation("Check 2", state, lambda: False)
        run_validation("Check 3", state, lambda: True, skip=True)

        assert state.total == 3
        assert state.passed == 1
        assert state.failed == 1
        assert state.skipped == 1
        assert len(state.results) == 3


# ---------------------------------------------------------------------------
# validate_session_end
# ---------------------------------------------------------------------------


class TestValidateSessionEnd:
    """Tests for session end validation."""

    def test_no_session_log_returns_true(self, tmp_path: Path) -> None:
        result = validate_session_end(tmp_path)
        assert result is True

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import MissingScriptSkip

        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("log", encoding="utf-8")
        # scripts/Validate-Session.ps1 does not exist (ADR-042 expungement).
        (tmp_path / "scripts").mkdir(exist_ok=True)

        import pytest

        with pytest.raises(MissingScriptSkip):
            validate_session_end(tmp_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _parse_yaml_frontmatter
# ---------------------------------------------------------------------------


class TestParseYamlFrontmatter:
    """Tests for YAML frontmatter parser."""

    def test_parses_valid_frontmatter(self) -> None:
        text = '---\nstatus: "APPROVED"\npriority: "P1"\nblocking: false\n---\n# Title\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"
        assert result["blocking"] is False

    def test_returns_none_without_frontmatter(self) -> None:
        text = "# Title\nSome content\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_returns_none_for_unclosed_frontmatter(self) -> None:
        text = "---\nstatus: APPROVED\n# No closing delimiter\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_parses_boolean_true(self) -> None:
        text = "---\nblocking: true\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["blocking"] is True

    def test_parses_integer_values(self) -> None:
        text = "---\npr: 1205\nissue: 937\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["pr"] == 1205
        assert result["issue"] == 937

    def test_strips_quotes(self) -> None:
        text = '---\nstatus: "BLOCKED"\nreviewer: \'architect\'\n---\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "BLOCKED"
        assert result["reviewer"] == "architect"

    def test_skips_comments_and_blank_lines(self) -> None:
        text = "---\n# comment\n\nstatus: APPROVED\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert len(result) == 1

    def test_strips_inline_yaml_comments(self) -> None:
        text = (
            "---\n"
            "status: APPROVED              # APPROVED | NEEDS_CHANGES\n"
            "priority: P1  # severity\n"
            "---\n"
        )
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"

    def test_preserves_hash_inside_quotes(self) -> None:
        text = '---\nvalue: "has # in it"\n---\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["value"] == "has # in it"

    def test_returns_none_for_malformed_yaml(self) -> None:
        text = (
            "---\n"
            "description: Agent examples: Context: user asks\n"
            "---\n"
        )
        assert _parse_yaml_frontmatter(text) is None


# ---------------------------------------------------------------------------
# validate_design_review_frontmatter
# ---------------------------------------------------------------------------


class TestValidateDesignReviewFrontmatter:
    """Tests for DESIGN-REVIEW frontmatter validation."""

    def _write_review(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper to create a DESIGN-REVIEW file."""
        review_dir = tmp_path / ".agents" / "architecture"
        review_dir.mkdir(parents=True, exist_ok=True)
        filepath = review_dir / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_no_directory_returns_true(self, tmp_path: Path) -> None:
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_no_review_files_returns_true(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "architecture").mkdir(parents=True)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_valid_frontmatter_passes(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_missing_frontmatter_fails(self, tmp_path: Path) -> None:
        content = "# Design Review: Test\nNo frontmatter here.\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_missing_required_fields_fails(self, tmp_path: Path) -> None:
        content = '---\nstatus: "APPROVED"\n---\n# Design Review: Test\n'
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_status_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "INVALID"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_priority_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P99"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_blocking_review_detected(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: true\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        # Blocking reviews still pass validation (they just warn)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_blocking_null_does_not_count_as_blocking(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: null\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)

        assert validate_design_review_frontmatter(tmp_path) is True

        captured = capsys.readouterr()
        assert "should have blocking: true" in captured.out
        assert "blocking review(s) detected" not in captured.out

    def test_multiple_files_all_valid(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", valid)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_one_invalid_among_valid_fails(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        invalid = "# No frontmatter\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", invalid)
        assert validate_design_review_frontmatter(tmp_path) is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.quick is False
        assert args.skip_tests is False
        assert args.verbose is False

    def test_quick_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--quick"])
        assert args.quick is True

    def test_skip_tests_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--skip-tests"])
        assert args.skip_tests is True

    def test_verbose_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True


class TestMain:
    """Integration tests for main entry point.

    External tool calls are mocked to avoid requiring actual tools.
    """

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_quick_mode_skips_slow_checks(
        self, mock_which: Any, mock_run: Any  # noqa: ANN401
    ) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        mock_which.return_value = "/usr/bin/tool"

        # Quick mode should skip path normalization, planning, agent drift, yaml style
        result = main(["--quick", "--skip-tests"])
        assert result == 0

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_all_pass_returns_zero(
        self, mock_which: Any, mock_run: Any  # noqa: ANN401
    ) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        mock_which.return_value = "/usr/bin/tool"

        # All external tools pass
        result = main(["--quick", "--skip-tests"])
        assert result == 0


# ---------------------------------------------------------------------------
# validate_markdown_lint
# ---------------------------------------------------------------------------


# Captured verbatim from markdownlint-cli2 v0.23.2 (markdownlint v0.41.1) on
# 2026-07-29. The tool splits output across both streams: this progress banner
# and the trailing summary go to stdout, while rule violations go to stderr.
# The banner is the only signal separating "checked and clean" from "never
# selected", because the summary counts files *with issues* and prints
# "0 issues in 0 files" for both.
def _clean_stdout(count: int) -> str:
    """Return real cli2 stdout for a run that selected `count` clean files."""
    unit = "file" if count == 1 else "files"
    return (
        "markdownlint-cli2 v0.23.2 (markdownlint v0.41.1)\n"
        f"Linting: {count} {unit}\n"
        "Summary: 0 issues in 0 files\n"
    )


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
                    mock_run.return_value = (0, _clean_stdout(2), "")
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2", "--fix", "README.md", "docs/guide.md"],
            cwd=tmp_path,
        )


    def test_skip_autofix_runs_check_only(
        self,
        tmp_path: Path,
        monkeypatch: Any,  # noqa: ANN401
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        monkeypatch.setenv("SKIP_AUTOFIX", "1")
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=["README.md"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, _clean_stdout(1), "")
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


# ---------------------------------------------------------------------------
# validate_dash_prohibition (Issue #1923, REQ-006-AC7, M4)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# validate_lefthook_installed
# ---------------------------------------------------------------------------


class TestValidateLefthookInstalled:
    """The local hook gate delegates to Lefthook through uv."""

    @staticmethod
    def _write_config(repo_root: Path) -> None:
        (repo_root / "lefthook.yml").write_text("pre-commit: {}\n", encoding="utf-8")

    def test_skipped_under_github_actions(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False):
            with pytest.raises(MissingScriptSkip):
                validate_lefthook_installed(tmp_path)

    def test_skipped_under_ci(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        with patch.dict("os.environ", {"CI": "1", "GITHUB_ACTIONS": "false"}):
            with pytest.raises(MissingScriptSkip):
                validate_lefthook_installed(tmp_path)

    def test_not_skipped_when_ci_is_false(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(0, "OK", "")):
                    assert validate_lefthook_installed(tmp_path) is True

    def test_missing_config_fails_closed(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            assert validate_lefthook_installed(tmp_path) is False

    def test_missing_uv_fails_closed(self, tmp_path: Path, capsys: Any) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value=None):
                assert validate_lefthook_installed(tmp_path) is False

        output = capsys.readouterr()
        assert "uv is unavailable" in output.err
        assert "Lefthook jobs run through uv" in output.err

    def test_direct_lefthook_does_not_bypass_missing_uv(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)

        def locate_tool(tool: str) -> str | None:
            return None if tool == "uv" else "/bin/lefthook"

        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch(
                "checks_plugin.shutil.which", side_effect=locate_tool
            ) as mock_which:
                with patch("checks_plugin._run_subprocess") as mock_run:
                    assert validate_lefthook_installed(tmp_path) is False

        assert mock_which.call_args_list == [call("uv")]
        mock_run.assert_not_called()

    def test_uses_uv_to_match_configured_hook_runtime(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv") as mock_which:
                with patch(
                    "checks_plugin._run_subprocess", return_value=(0, "OK", "")
                ) as mock_run:
                    assert validate_lefthook_installed(tmp_path) is True

        assert mock_which.call_args_list == [call("uv")]
        mock_run.assert_called_once_with(
            ["/bin/uv", "run", "--frozen", "lefthook", "check-install"],
            cwd=tmp_path,
        )

    def test_passes_when_check_install_exits_zero(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "OK", "")
                    assert validate_lefthook_installed(tmp_path) is True
        mock_run.assert_called_once_with(
            ["/bin/uv", "run", "--frozen", "lefthook", "check-install"],
            cwd=tmp_path,
        )

    def test_fails_when_check_install_exits_nonzero(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(1, "", "missing")):
                    with patch("checks_plugin._is_linked_worktree", return_value=False):
                        assert validate_lefthook_installed(tmp_path) is False

        output = capsys.readouterr()
        assert (
            "uv run --frozen lefthook install --reset-hooks-path" in output.out
        )
        assert "uv run --frozen lefthook check-install" in output.out

    def test_warns_not_fails_in_linked_worktree(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(1, "", "missing")):
                    with patch("checks_plugin._is_linked_worktree", return_value=True):
                        assert validate_lefthook_installed(tmp_path) is True

        output = capsys.readouterr()
        assert (
            "uv run --frozen lefthook install --reset-hooks-path" in output.out
        )
        assert "uv run --frozen lefthook check-install" in output.out


class TestIsLinkedWorktree:
    """The git-hooks gate downgrades to a warning in a linked worktree (#2374)."""

    def test_true_when_git_dir_differs_from_common_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (
                    0,
                    "/repo/.git/worktrees/wt\n/repo/.git\n",
                    "",
                )
                assert _is_linked_worktree(tmp_path) is True

    def test_false_when_git_dir_equals_common_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (0, "/repo/.git\n/repo/.git\n", "")
                assert _is_linked_worktree(tmp_path) is False

    def test_false_when_git_missing(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value=None):
            assert _is_linked_worktree(tmp_path) is False

    def test_false_when_rev_parse_fails(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (128, "", "fatal: not a git repository")
                assert _is_linked_worktree(tmp_path) is False

    def test_false_when_output_malformed(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (0, "only-one-line\n", "")
                assert _is_linked_worktree(tmp_path) is False

    def test_relative_paths_are_anchored_to_repo_root(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        repo = tmp_path / "repo"
        repo.mkdir()
        common = repo / "common"
        common.mkdir()
        (repo / ".git").symlink_to(common, target_is_directory=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / ".git").mkdir()
        monkeypatch.chdir(outside)

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (0, ".git\ncommon\n", "")
                assert _is_linked_worktree(repo) is False

        command = mock_run.call_args.args[0]
        assert "--path-format=absolute" not in command


class TestValidateWorkflowYaml:
    """Workflow validation raises the shellcheck severity floor to warning (#2374)."""

    def test_returns_true_when_actionlint_missing(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        with patch("checks_tooling.shutil.which", return_value=None):
            assert validate_workflow_yaml(tmp_path) is True

    def test_returns_true_when_no_workflow_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            assert validate_workflow_yaml(tmp_path) is True

    def test_passes_shellcheck_severity_warning_env(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

            env_kwarg = mock_run.call_args.kwargs["env"]
            assert "--severity=warning" in env_kwarg["SHELLCHECK_OPTS"]

    def test_preserves_existing_shellcheck_opts(self, tmp_path: Path) -> None:
        import os

        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch.dict(os.environ, {"SHELLCHECK_OPTS": "--exclude=SC1091"}, clear=False):
            with patch(
                "checks_tooling.shutil.which", return_value="actionlint"
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_workflow_yaml(tmp_path) is True

                opts = mock_run.call_args.kwargs["env"]["SHELLCHECK_OPTS"]
                assert "--exclude=SC1091" in opts
                assert "--severity=warning" in opts

    def test_fails_when_actionlint_reports_warning(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (1, "ci.yml:1:1: SC2034 ... [shellcheck]", "")
                assert validate_workflow_yaml(tmp_path) is False


# ---------------------------------------------------------------------------
# validate_workflow_yaml (actionlint scoping, issue #2346)
# ---------------------------------------------------------------------------


class TestValidateWorkflowYamlScope:
    """actionlint validates workflows only; composite action.yml files under
    .github/actions/ must never be passed to it (issue #2346)."""

    @staticmethod
    def _build_tree(root: Path) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n",
            encoding="utf-8",
        )
        actions = root / ".github" / "actions" / "composite"
        actions.mkdir(parents=True)
        # A composite action: actionlint would emit false errors if scanned.
        (actions / "action.yml").write_text(
            "name: composite\nruns:\n  using: composite\n  steps: []\n",
            encoding="utf-8",
        )

    def test_does_not_pass_composite_action_paths(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        assert command[0] == "actionlint"
        paths = command[1:]
        # No composite action path is ever handed to actionlint.
        assert all(".github/actions" not in p for p in paths)
        assert not any(p.endswith("action.yml") for p in paths)

    def test_passes_only_workflow_files(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                validate_workflow_yaml(tmp_path)

        command = mock_run.call_args.args[0]
        paths = command[1:]
        assert paths, "expected at least one workflow file to be scanned"
        workflows_prefix = str(tmp_path / ".github" / "workflows")
        assert all(p.startswith(workflows_prefix) for p in paths)

    def test_skips_when_actionlint_absent(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value=None):
            with patch("checks_tooling._run_subprocess") as mock_run:
                assert validate_workflow_yaml(tmp_path) is True
        mock_run.assert_not_called()


class TestValidateVendorPortability:
    """The vendor-portability gate wraps check_vendor_portability.py (#2050).

    Exit-code contract mirrored from the wrapped script:
    0 (no new offenders / no scan roots) -> pass, 1 (new offender) -> fail,
    2 (config error) -> fail. A missing wrapped script raises MissingScriptSkip.
    """

    def _make_repo(self, tmp_path: Path) -> Path:
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "check_vendor_portability.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        return tmp_path

    def test_passes_when_checker_exits_zero(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (0, "[PASS] No new vendor-portability offenders.\n", "")
            assert validate_vendor_portability(repo) is True

    def test_fails_on_new_offender_exit_one(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (1, "[FAIL] 1 new vendor-portability offender(s).\n", "")
            assert validate_vendor_portability(repo) is False

    def test_fails_on_config_error_exit_two(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (2, "", "[FAIL] repo root not found")
            assert validate_vendor_portability(repo) is False

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import (
            MissingScriptSkip,
            validate_vendor_portability,
        )

        with pytest.raises(MissingScriptSkip):
            validate_vendor_portability(tmp_path)

    def test_passes_repo_root_to_checker(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (0, "", "")
            validate_vendor_portability(repo)

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        repo_root_index = command.index("--repo-root")
        assert command[repo_root_index + 1] == str(repo)


# ---------------------------------------------------------------------------
# validate_review_marker  (Issue #1938)
# ---------------------------------------------------------------------------


class TestValidateReviewMarker:
    """Tests for the SHA-bound /review marker advisory check.

    Behavior contract:

    - Script missing, ``REVIEW_MARKER_ENFORCED`` unset / 0: returns ``True``
      (advisory skip; never blocks pre-PR).
    - Script missing, ``REVIEW_MARKER_ENFORCED=1``: returns ``False``.
    - Script present, HEAD has a binding marker: returns ``True`` regardless
      of enforcement.
    - Script present, HEAD has no marker, advisory: returns ``True``.
    - Script present, HEAD has no marker, enforced: returns ``False``.
    """

    import subprocess as _subprocess

    @staticmethod
    def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
        result = TestValidateReviewMarker._subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            input=stdin,
            check=True,
        )
        return result.stdout.strip()

    def _make_repo(self, tmp_path: Path, with_script: bool) -> Path:
        """Build a fake repo: real validator script (optionally) + git history."""
        repo = tmp_path / "repo"
        repo.mkdir()
        if with_script:
            dest = repo / "scripts" / "validation"
            dest.mkdir(parents=True)
            real = (
                Path(__file__).resolve().parent.parent
                / "scripts"
                / "validation"
                / "validate_review_marker.py"
            )
            (dest / "validate_review_marker.py").write_text(
                real.read_text(encoding="utf-8"), encoding="utf-8"
            )
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Tester")
        self._git(repo, "config", "commit.gpgsign", "false")
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "feat: one")
        (repo / "b.txt").write_text("y\n", encoding="utf-8")
        self._git(repo, "add", "b.txt")
        self._git(repo, "commit", "-q", "-m", "feat: two")
        return repo

    def _add_marker(self, repo: Path) -> None:
        """Add an empty /review marker commit binding the current tip."""
        tip = self._git(repo, "rev-parse", "HEAD")
        self._git(
            repo,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "review: marker",
            "--trailer",
            f"Reviewed-By: /review@analyst,security on {tip}",
        )

    def test_missing_script_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_missing_script_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_no_marker_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_no_marker_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_valid_marker_passes_advisory(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_valid_marker_passes_enforced(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is True


class TestValidateCiDependencyPinsSkipsBeforeImporting:
    """The skip path must survive a tree that cannot import the checker.

    ``check_ci_dependency_pins`` imports ``packaging``. A downstream install
    with no ``.github/`` tree is also the install least likely to carry dev
    dependencies, so importing before the existence check would raise
    ImportError on exactly the tree the function is written to skip. Issue #3377.
    """

    @staticmethod
    def _block_import(monkeypatch: Any) -> None:  # noqa: ANN401
        import sys

        # A None entry makes ``import check_ci_dependency_pins`` raise
        # ImportError, which is what a missing ``packaging`` looks like from
        # the caller's side.
        monkeypatch.setitem(sys.modules, "check_ci_dependency_pins", None)

    def test_an_absent_github_tree_skips_without_importing(
        self,
        tmp_path: Path,
        monkeypatch: Any,  # noqa: ANN401
    ) -> None:
        from checks_tooling import validate_ci_dependency_pins

        from scripts.validation.pre_pr import MissingScriptSkip

        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        self._block_import(monkeypatch)
        with pytest.raises(MissingScriptSkip):
            validate_ci_dependency_pins(tmp_path)

    def test_an_absent_pyproject_skips_without_importing(
        self,
        tmp_path: Path,
        monkeypatch: Any,  # noqa: ANN401
    ) -> None:
        from checks_tooling import validate_ci_dependency_pins

        from scripts.validation.pre_pr import MissingScriptSkip

        (tmp_path / ".github").mkdir()
        self._block_import(monkeypatch)
        with pytest.raises(MissingScriptSkip):
            validate_ci_dependency_pins(tmp_path)

    def test_a_present_tree_still_imports_and_runs(self, tmp_path: Path) -> None:
        """Negative control: a bad pin returns False, proving the checker ran."""
        from checks_tooling import validate_ci_dependency_pins

        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "w.yml").write_text(
            "run: pip install pytest==8.0.0\n", encoding="utf-8"
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname="x"\ndependencies=["pytest>=9.0.3"]\n', encoding="utf-8"
        )
        assert validate_ci_dependency_pins(tmp_path) is False


# ---------------------------------------------------------------------------
# Issue #3710: a markdown gate that selects nothing must not report success
# ---------------------------------------------------------------------------


class TestMarkdownLintReportsWhatItActuallyChecked:
    """A PASS on zero selected files is 'not linted', not 'clean'.

    `.markdownlint-cli2.yaml` excludes 89.7% of tracked markdown (3,529 of
    3,935 files as of 2026-07-29) through 44 `ignores` patterns. Naming an
    excluded path on the command line selects zero files and exits 0, so the
    gate printed nothing and returned True on markdown it never read. The
    exclusions are deliberate, so the fix is an honest message, not a hard
    failure.
    """

    def _run(
        self,
        tmp_path: Path,
        targets: list[str] | None,
        result: tuple[int, str, str],
        capsys: pytest.CaptureFixture[str],
    ) -> tuple[bool, str]:
        from scripts.validation.pre_pr import validate_markdown_lint

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets", return_value=targets
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = result
                    outcome = validate_markdown_lint(tmp_path)
        return outcome, capsys.readouterr().out

    def test_zero_selected_files_warns_instead_of_passing_silently(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outcome, out = self._run(
            tmp_path,
            [".agents/analysis/notes.md"],
            (0, _clean_stdout(0), ""),
            capsys,
        )

        assert outcome is True, "excluded paths are deliberate, so do not fail"
        assert "0 of 1 target" in out
        assert "This PASS means 'not linted', not 'clean'." in out

    def test_a_fully_selected_clean_run_stays_quiet(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outcome, out = self._run(
            tmp_path, ["README.md"], (0, _clean_stdout(1), ""), capsys
        )

        assert outcome is True
        assert "WARNING" not in out, "a fully checked run has nothing to report"

    def test_a_partially_excluded_run_names_the_shortfall(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outcome, out = self._run(
            tmp_path,
            ["README.md", ".agents/analysis/notes.md"],
            (0, _clean_stdout(1), ""),
            capsys,
        )

        assert outcome is True
        assert "checked 1 of 2 target" in out

    def test_an_unreadable_banner_admits_the_count_is_unknown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Guards against a future cli2 release renaming the banner: the parser
        # must say it could not tell rather than claim full coverage.
        outcome, out = self._run(
            tmp_path,
            ["README.md"],
            (0, "Checked: 1 document\nSummary: 0 issues in 0 files\n", ""),
            capsys,
        )

        assert outcome is True
        assert "could not read the 'Linting: N files' banner" in out

    def test_the_full_repo_fallback_does_not_warn_about_its_own_glob(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # `_markdown_lint_targets` returns None when scope is unknown and the
        # command becomes a single `**/*.md` glob. Comparing 406 linted files
        # against one glob argument would warn on every clean full-repo run.
        outcome, out = self._run(
            tmp_path, None, (0, _clean_stdout(406), ""), capsys
        )

        assert outcome is True
        assert "WARNING" not in out

    def test_a_full_repo_run_that_matches_nothing_still_warns(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outcome, out = self._run(
            tmp_path, None, (0, _clean_stdout(0), ""), capsys
        )

        assert outcome is True
        assert "0 of 1 target" in out

    def test_failures_print_the_violations_the_tool_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The defect behind the canned advice: violations arrive on stderr and
        # the caller discarded it, so an MD041 reached the operator as advice
        # about MD040 and MD033.
        violations = (
            "docs/guide.md:1 error MD041/first-line-heading/first-line-h1 "
            'First line in a file should be a top-level heading [Context: "Text"]\n'
            "docs/guide.md:2 error MD032/blanks-around-lists Lists should be "
            'surrounded by blank lines [Context: "- a"]\n'
        )
        outcome, out = self._run(
            tmp_path,
            ["docs/guide.md"],
            (1, "Linting: 1 file\nSummary: 2 issues in 1 file\n", violations),
            capsys,
        )

        assert outcome is False
        assert "MD041/first-line-heading" in out
        assert "MD032/blanks-around-lists" in out
        assert "docs/guide.md:2" in out

    def test_a_failure_omits_the_thousand_character_exclusion_banner(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # cli2 restates all 44 exclusion globs on one `Finding:` line. Printing
        # stdout alongside stderr buried the lines that named the rule.
        finding = "Finding: docs/guide.md " + " ".join(
            f"!excluded/{n}/**" for n in range(44)
        )
        outcome, out = self._run(
            tmp_path,
            ["docs/guide.md"],
            (
                1,
                f"{finding}\nLinting: 1 file\nSummary: 1 issues in 1 file\n",
                "docs/guide.md:1 error MD041/first-line-heading\n",
            ),
            capsys,
        )

        assert outcome is False
        assert "MD041" in out
        assert "!excluded/0/**" not in out

    def test_a_failure_with_no_stderr_falls_back_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Failure modes that never reach the violation reporter, such as an
        # unparsable config, report on stdout only. Dropping stdout entirely
        # would restore the silence this issue is about.
        outcome, out = self._run(
            tmp_path,
            ["docs/guide.md"],
            (2, "Unable to parse JSONC in .markdownlint-cli2.jsonc\n", ""),
            capsys,
        )

        assert outcome is False
        assert "Unable to parse JSONC" in out
