"""Markdown lint and dash-prohibition tests for scripts.validation.pre_pr.

Split from tests/test_validation_pre_pr.py (issue #4352). Covers:
- validate_markdown_lint
- validate_dash_prohibition
- markdown-lint reporting accuracy
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation import checks_common
from scripts.validation.pre_pr import main, validate_dash_prohibition, validate_markdown_lint


def _clean_stdout(count: int) -> str:
    """Return real cli2 stdout for a run that selected `count` clean files."""
    unit = "file" if count == 1 else "files"
    return (
        "markdownlint-cli2 v0.23.2 (markdownlint v0.41.1)\n"
        f"Linting: {count} {unit}\n"
        "Summary: 0 issues in 0 files\n"
    )


def test_subprocess_resolves_windows_command_shim() -> None:
    completed = checks_common.subprocess.CompletedProcess(
        ["npx.cmd", "--version"],
        0,
        "11.17.0\n",
        "",
    )
    with (
        patch.object(
            checks_common,
            "resolve_executable",
            return_value=r"C:\Program Files\nodejs\npx.cmd",
        ) as resolver,
        patch.object(checks_common.subprocess, "run", return_value=completed) as run,
    ):
        result = checks_common._run_subprocess(["npx", "--version"])

    assert result == (0, "11.17.0\n", "")
    resolver.assert_called_once_with("npx", env=None)
    assert run.call_args.args[0] == [
        r"C:\Program Files\nodejs\npx.cmd",
        "--version",
    ]


class TestValidateMarkdownLint:
    """Markdown linting checks branch changes without masking unknown scope."""

    def test_returns_true_when_branch_has_no_markdown(self, tmp_path: Path) -> None:

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=[],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_not_called()

    def test_lints_changed_markdown_only(self, tmp_path: Path) -> None:

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=["README.md", "docs/guide.md"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, _clean_stdout(2), "")
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_called_once_with(
            [
                "npx",
                "markdownlint-cli2@0.23.1",
                "--fix",
                "--",
                "README.md",
                "docs/guide.md",
            ],
            cwd=tmp_path,
        )


    def test_skip_autofix_runs_check_only(
        self,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:

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
            ["npx", "markdownlint-cli2@0.23.1", "--", "README.md"],
            cwd=tmp_path,
        )

    def test_falls_back_to_full_repo_when_scope_is_unknown(
        self, tmp_path: Path
    ) -> None:

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=None,
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (1, "", "markdownlint failed")
                    assert validate_markdown_lint(tmp_path) is False

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2@0.23.1", "--fix", "--", "**/*.md"],
            cwd=tmp_path,
        )

    def test_reports_explicit_targets_ignored_by_markdownlint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:

        target = tmp_path / ".agents" / "analysis" / "p2" / "x.md"
        target.parent.mkdir(parents=True)
        target.write_text("not a heading\n- missing blank before list\n", encoding="utf-8")

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (
                    0,
                    "Linting: 0 files\nSummary: 0 issues in 0 files\n",
                    "",
                )
                assert validate_markdown_lint(
                    tmp_path,
                    explicit_targets=[".agents/analysis/p2/x.md"],
                ) is True

        mock_run.assert_called_once_with(
            [
                "npx",
                "markdownlint-cli2@0.23.1",
                "--fix",
                "--",
                ".agents/analysis/p2/x.md",
            ],
            cwd=tmp_path,
        )
        out = capsys.readouterr().out
        assert "0 of 1 target" in out
        assert "not linted" in out

    def test_reports_explicit_targets_linted_cleanly(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:

        target = tmp_path / "README.md"
        target.write_text("# Title\n", encoding="utf-8")

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (
                    0,
                    "Linting: 1 files\nSummary: 0 issues in 0 files\n",
                    "",
                )
                assert validate_markdown_lint(
                    tmp_path,
                    explicit_targets=["README.md"],
                ) is True

        assert "WARNING" not in capsys.readouterr().out

    def test_explicit_targets_are_passed_after_option_delimiter(
        self, tmp_path: Path
    ) -> None:

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (
                    0,
                    "Linting: 1 files\nSummary: 0 issues in 0 files\n",
                    "",
                )
                assert validate_markdown_lint(
                    tmp_path,
                    explicit_targets=["-leading.md"],
                ) is True

        command = mock_run.call_args.args[0]
        assert command[-2:] == ["--", "-leading.md"]

    def test_markdown_lint_only_cli_uses_positional_targets(self) -> None:
        with patch("scripts.validation.pre_pr.validate_markdown_lint") as mock_lint:
            mock_lint.return_value = True
            assert main(["--markdown-lint-only", "--", "README.md"]) == 0

        mock_lint.assert_called_once()
        assert mock_lint.call_args.args[1] == ["README.md"]


# ---------------------------------------------------------------------------
# validate_dash_prohibition (Issue #1923, REQ-006-AC7, M4)
# ---------------------------------------------------------------------------


class TestValidateDashProhibition:
    """Tests for the branch-wide em/en-dash check."""

    def test_returns_true_when_no_base_ref_resolves(self, tmp_path: Path) -> None:

        # tmp_path is not a git repo; no ref will resolve.
        assert validate_dash_prohibition(tmp_path) is True

    def test_returns_true_for_clean_branch(self, tmp_path: Path) -> None:

        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "README.md\n", ""),  # git diff
                (0, "clean content\n", ""),  # git show
            ]
            assert validate_dash_prohibition(tmp_path) is True

    def test_returns_false_on_em_dash(self, tmp_path: Path) -> None:

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

        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "range.md\n", ""),
                (0, f"range 1{chr(0x2013)}10\n", ""),
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_skips_vendored_paths(self, tmp_path: Path) -> None:

        vendored = tmp_path / "node_modules" / "pkg" / "README.md"
        vendored.parent.mkdir(parents=True)
        vendored.write_text(f"upstream prose with {chr(0x2014)} dash\n", encoding="utf-8")
        with patch("checks_dash._resolve_branch_base_ref") as mock_ref, \
             patch("checks_dash._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "node_modules/pkg/README.md\n", "")
            assert validate_dash_prohibition(tmp_path) is True

    def test_skips_test_fixtures_dir(self, tmp_path: Path) -> None:

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
