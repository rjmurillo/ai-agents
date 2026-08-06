"""Tests for the advisory YAML style check (``validate_yaml_style``, yamllint).

Covers ``_yaml_style_targets`` (the branch-scoping helper) and the wiring in
``validate_yaml_style`` that decides between an immediate pass, a scoped
yamllint invocation, and the full-repo fallback. yamllint findings are
advisory: a scoped or full-repo run that finds style issues still returns
``True`` (see ``validate_yaml_style``'s docstring in ``checks_tooling.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import validate_yaml_style


class TestYamlStyleTargets:
    """Unit tests for ``_yaml_style_targets``, the branch-scoping helper.

    Covers only the extension-filtering contract specific to this gate
    (which files qualify, deleted-file exclusion). The base-ref/command-
    failure scoping contract itself (shared by every gate that calls
    ``_changed_paths_since_base``) is proven once in
    ``tests/validation_pre_pr/test_changed_paths_since_base.py``, not
    re-verified here.
    """

    @pytest.mark.parametrize(
        ("diff_stdout", "on_disk", "expected"),
        [
            ("README.md\0config.yml", ["config.yml"], ["config.yml"]),
            ("a.yml\0b.yaml\0c.txt", ["a.yml", "b.yaml"], ["a.yml", "b.yaml"]),
            ("removed.yml", [], []),
        ],
        ids=["changed-subset-returned", "both-extensions-matched", "deleted-file-excluded"],
    )
    def test_filtering_contract(
        self,
        tmp_path: Path,
        diff_stdout: str,
        on_disk: list[str],
        expected: list[str],
    ) -> None:
        """Only ``*.yml``/``*.yaml`` paths still present on disk qualify; a
        diff entry with no matching working-tree file cannot be linted.

        ``diff_stdout`` is NUL-delimited (matching the ``-z`` flag the shared
        helper now always passes); ``mock_run.return_value`` applies
        uniformly to all three underlying git calls the helper makes.
        """
        from checks_tooling import _yaml_style_targets

        for name in on_disk:
            (tmp_path / name).write_text("a: 1\n", encoding="utf-8")
        with patch("checks_tooling._resolve_branch_base_ref", return_value="origin/main"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, diff_stdout, "")
                assert _yaml_style_targets(tmp_path) == expected


class TestYamlStyleTargetsWorktreeOnly:
    """Real-repo regression: a YAML file edited only in the worktree (never
    committed, never staged) must still be scoped in.

    Guards the specific gate wiring (``_yaml_style_targets``'s extension
    filtering) against the union added to the shared
    ``_changed_paths_since_base`` helper; the union mechanics themselves are
    covered generically in ``test_changed_paths_since_base.py``.
    """

    def test_uncommitted_yaml_edit_is_scoped_in(
        self,
        tmp_path: Path,
        make_repo_with_base: Any,
        no_gh: None,
    ) -> None:
        from checks_tooling import _yaml_style_targets

        repo = make_repo_with_base(tmp_path)
        (repo / "config.yml").write_text("a: 1\n", encoding="utf-8")
        # Deliberately NOT committed and NOT staged: pure worktree edit.

        assert _yaml_style_targets(repo) == ["config.yml"]


class TestValidateYamlStyle:
    """Wiring tests: ``validate_yaml_style`` honors the three scope outcomes."""

    def test_returns_true_when_yamllint_missing(self, tmp_path: Path) -> None:
        with patch("checks_tooling.shutil.which", return_value=None):
            with patch("checks_tooling._run_subprocess") as mock_run:
                assert validate_yaml_style(tmp_path) is True
        mock_run.assert_not_called()

    def test_empty_scope_passes_without_invoking_yamllint(self, tmp_path: Path) -> None:
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/yamllint"):
            with patch("checks_tooling._yaml_style_targets", return_value=[]):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    assert validate_yaml_style(tmp_path) is True
        mock_run.assert_not_called()

    def test_scoped_subset_is_passed_to_yamllint(self, tmp_path: Path) -> None:
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/yamllint"):
            with patch(
                "checks_tooling._yaml_style_targets",
                return_value=["config.yml", "workflows/ci.yml"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_yaml_style(tmp_path) is True

        command = mock_run.call_args.args[0]
        assert command == [
            "yamllint",
            "-f",
            "parsable",
            str(tmp_path / "config.yml"),
            str(tmp_path / "workflows/ci.yml"),
        ]

    def test_none_scope_falls_back_to_full_repo_scan(self, tmp_path: Path) -> None:
        """An unproven scope (no base ref / diff failure) must not skip the check."""
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/yamllint"):
            with patch("checks_tooling._yaml_style_targets", return_value=None):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_yaml_style(tmp_path) is True

        command = mock_run.call_args.args[0]
        assert command == ["yamllint", "-f", "parsable", str(tmp_path)]

    def test_scoped_findings_are_advisory_and_still_pass(self, tmp_path: Path) -> None:
        """yamllint findings warn but never fail (advisory tool, #2374 precedent)."""
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/yamllint"):
            with patch(
                "checks_tooling._yaml_style_targets", return_value=["config.yml"]
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (
                        1,
                        "config.yml:1:1: [warning] missing document start (document-start)",
                        "",
                    )
                    assert validate_yaml_style(tmp_path) is True

    def test_scoped_path_with_space_is_quoted_as_a_single_argv_element(
        self, tmp_path: Path
    ) -> None:
        """A path with a space must survive as one argv element, not split.

        ``_run_subprocess`` invokes yamllint via ``subprocess.run`` with a
        list (no shell), so this proves the file list is built from
        ``repo_root / path`` without shell-style joining that could split on
        whitespace.
        """
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/yamllint"):
            with patch(
                "checks_tooling._yaml_style_targets",
                return_value=["release notes/changelog.yml"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_yaml_style(tmp_path) is True

        command = mock_run.call_args.args[0]
        assert command == [
            "yamllint",
            "-f",
            "parsable",
            str(tmp_path / "release notes/changelog.yml"),
        ]
        # Exactly one argv element for the file, not two from a whitespace split.
        assert len(command) == 4
