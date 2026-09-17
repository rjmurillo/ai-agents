"""Markdown and prose validation tests for pre-PR checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _clean_stdout(count: int) -> str:
    """Return real cli2 stdout for a run that selected ``count`` clean files."""
    unit = "file" if count == 1 else "files"
    return (
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
                    mock_run.return_value = (0, "", "")
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2@0.23.1", "--fix", "--", "README.md", "docs/guide.md"],
            cwd=tmp_path,
        )

    def test_excludes_session_scratch_from_markdown_lint_command(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
        changed = [
            "README.md",
            "worktrees/sub/notes.md",
            ".agent-scratch/sub/notes.md",
            ".scratch/sub/notes.md",
        ]
        with patch(
            "checks_changed_paths._changed_paths_since_base",
            return_value=changed,
        ):
            with patch("checks_tooling.shutil.which", return_value="npx"):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "Linting: 1 file\n", "")
                    assert validate_markdown_lint(tmp_path) is True

        mock_run.assert_called_once_with(
            ["npx", "markdownlint-cli2@0.23.1", "--fix", "--", "README.md"],
            cwd=tmp_path,
        )

    def test_skip_autofix_runs_check_only(self, tmp_path: Path, monkeypatch: Any) -> None:
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
            ["npx", "markdownlint-cli2@0.23.1", "--", "README.md"],
            cwd=tmp_path,
        )

    def test_batches_large_target_lists(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        targets = [f"docs/{index}.md" for index in range(101)]
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch("checks_tooling._markdown_lint_targets", return_value=targets):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.side_effect = [
                        (0, _clean_stdout(100), ""),
                        (0, _clean_stdout(1), ""),
                    ]
                    assert validate_markdown_lint(tmp_path) is True

        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0].args[0][-100:] == targets[:100]
        assert mock_run.call_args_list[1].args[0][-1:] == targets[100:]

    def test_batches_rendered_windows_command_before_limit(
        self, tmp_path: Path
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        targets = [f"docs/{character} {character * 3_720}.md" for character in ("a", "b")]
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch("checks_tooling._markdown_lint_targets", return_value=targets):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.side_effect = [
                        (0, _clean_stdout(1), ""),
                        (0, _clean_stdout(1), ""),
                    ]
                    assert validate_markdown_lint(tmp_path) is True

        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0].args[0][-1] == targets[0]
        assert mock_run.call_args_list[1].args[0][-1] == targets[1]

    def test_rejects_single_target_that_exceeds_windows_limit(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        target = f"docs/long path/{'a' * 7_500}.md"
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=[target],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    assert validate_markdown_lint(tmp_path) is False

        mock_run.assert_not_called()
        output = capsys.readouterr().out
        assert "cannot fit under the Windows command-line limit" in output
        assert "7,500" in output

    def test_counts_non_bmp_targets_as_two_windows_code_units(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        target = f"docs/{'😀' * 4_000}.md"
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=[target],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    assert validate_markdown_lint(tmp_path) is False

        mock_run.assert_not_called()
        output = capsys.readouterr().out
        assert "cannot fit under the Windows command-line limit" in output
        measured = re.search(r"renders to ([\d,]+) UTF-16 code units", output)
        assert measured is not None
        assert int(measured.group(1).replace(",", "")) > 7_500

    def test_empty_tool_failure_reports_exit_code_without_rule_guesses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch(
                "checks_tooling._markdown_lint_targets",
                return_value=["README.md"],
            ):
                with patch(
                    "checks_tooling._run_subprocess",
                    return_value=(249, "", ""),
                ):
                    assert validate_markdown_lint(tmp_path) is False

        output = capsys.readouterr().out
        assert "exit code 249" in output
        assert "produced no stdout or stderr" in output
        assert "Common issues" not in output

    def test_failed_batch_does_not_skip_later_autofix_targets(
        self, tmp_path: Path
    ) -> None:
        from scripts.validation.pre_pr import validate_markdown_lint

        targets = [f"docs/{character * 4_000}.md" for character in ("a", "b")]
        with patch("checks_tooling.shutil.which", return_value="npx"):
            with patch("checks_tooling._markdown_lint_targets", return_value=targets):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.side_effect = [
                        (249, "", ""),
                        (0, _clean_stdout(1), ""),
                    ]
                    assert validate_markdown_lint(tmp_path) is False

        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1].args[0][-1] == targets[1]

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
            ["npx", "markdownlint-cli2@0.23.1", "--fix", "--", "**/*.md"],
            cwd=tmp_path,
        )


class TestMarkdownLintTargets:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("README.md", True),
            ("worktrees/session/notes.md", False),
            (".agent-scratch/session/notes.md", False),
            (".scratch/session/notes.md", False),
            ("docs/worktrees/session/notes.md", True),
            ("worktrees/session/notes.txt", False),
        ],
    )
    def test_filters_only_root_scratch_markdown(
        self, tmp_path: Path, path: str, expected: bool
    ) -> None:
        from scripts.validation.pre_pr import _markdown_lint_targets

        with patch("checks_tooling._filtered_targets") as mock_filtered:
            mock_filtered.side_effect = lambda _root, _label, predicate: [
                path
            ] if predicate(path) else []

            result = _markdown_lint_targets(tmp_path)

        assert result == ([path] if expected else [])
