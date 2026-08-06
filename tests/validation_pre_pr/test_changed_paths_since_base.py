"""Tests for the shared changed-path discovery helper ``_changed_paths_since_base``.

Consolidates the scoping-contract and command-construction tests that used to
be duplicated across ``test_workflow_checks.py::TestWorkflowYamlTargets`` and
``test_yaml_style_checks.py::TestYamlStyleTargets``: both exercised the SAME
underlying ``_changed_paths_since_base`` behavior through their gate-specific
wrapper (``_workflow_yaml_targets`` / ``_yaml_style_targets``), so a change to
the shared helper had to be re-verified (and could drift) in two places. This
file is the one place that behavior is proven; each gate file keeps only the
filtering/wiring tests that are actually specific to that gate (extension
matching, composite-action exclusion, deleted-file exclusion, argv
construction for the linter itself).

``_changed_paths_since_base`` unions three git signals (issue: a prior
version only diffed the committed range against the base ref, so a
worktree-only edit -- staged, unstaged, or untracked -- was invisible to
every gate that scoped itself this way):

1. Committed changes since the base ref (``<base>...HEAD``).
2. Uncommitted changes against HEAD (covers the index AND the working tree
   in one ``git diff HEAD`` call).
3. Untracked files (``git ls-files --others --exclude-standard``).

All three run NUL-delimited (``-z``) so Unicode and space-containing paths
survive intact.

``git_cmd``, ``make_repo_with_base``, and ``no_gh`` are fixtures from
``tests/validation_pre_pr/conftest.py``, shared with the worktree-only-change
regression tests in ``test_workflow_checks.py`` and ``test_yaml_style_checks.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

# `checks_tooling.py` is a script module, not a package member; it inserts
# its own directory onto `sys.path` when imported via `scripts.validation.*`
# (see its `_SCRIPT_DIR` guard), but that only helps a module that imports
# `scripts.validation.pre_pr` FIRST. Doing the same insert directly here
# makes this file's import self-contained instead of depending on another
# test module having already run its own top-level import first (an
# ordering `ruff --fix`'s import sort is not aware of and will happily
# rearrange out from under).
_SCRIPTS_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_SCRIPTS_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_VALIDATION_DIR))

from checks_tooling import _changed_paths_since_base  # noqa: E402

pytestmark = pytest.mark.usefixtures("no_gh")

GitCmd = Callable[..., CompletedProcess[str]]
RepoFactory = Callable[[Path], Path]


# ---------------------------------------------------------------------------
# Scoping contract: base ref resolution and command-failure fallback
# ---------------------------------------------------------------------------


class TestScopingContract:
    """None means "full-scan fallback"; [] means "resolved, nothing changed"."""

    def test_returns_none_when_no_base_ref_resolves(self, tmp_path: Path) -> None:
        # tmp_path is not a git repo at all; no ref can resolve.
        with patch("checks_tooling._run_subprocess") as mock_run:
            assert _changed_paths_since_base(tmp_path, "Test") is None
        mock_run.assert_not_called()

    @pytest.mark.parametrize(
        "failing_call_index",
        [0, 1, 2],
        ids=["committed-diff-fails", "worktree-diff-fails", "ls-files-fails"],
    )
    def test_returns_none_when_any_underlying_command_fails(
        self, tmp_path: Path, failing_call_index: int
    ) -> None:
        """A git-command failure is a proof failure, not a "no changes"
        signal, regardless of which of the three commands fails."""
        with patch(
            "checks_tooling._resolve_branch_base_ref", return_value="origin/main"
        ):
            results = [(0, "", ""), (0, "", ""), (0, "", "")]
            results[failing_call_index] = (128, "", "fatal: bad revision")
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.side_effect = results
                assert _changed_paths_since_base(tmp_path, "Test") is None

    def test_returns_empty_list_for_a_clean_resolved_branch(self, tmp_path: Path) -> None:
        with patch(
            "checks_tooling._resolve_branch_base_ref", return_value="origin/main"
        ):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert _changed_paths_since_base(tmp_path, "Test") == []

    def test_issues_exactly_three_calls_in_order_with_acmr_and_z(
        self, tmp_path: Path
    ) -> None:
        """Locks in the three-command shape: committed range, worktree-vs-HEAD,
        untracked -- each NUL-delimited, the two diffs ACMR-filtered."""
        with patch(
            "checks_tooling._resolve_branch_base_ref", return_value="origin/main"
        ):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                _changed_paths_since_base(tmp_path, "Test")

        assert mock_run.call_args_list == [
            (
                (
                    [
                        "git",
                        "-C",
                        str(tmp_path),
                        "diff",
                        "--name-only",
                        "-z",
                        "--diff-filter=ACMR",
                        "origin/main...HEAD",
                    ],
                ),
                {"timeout": 30},
            ),
            (
                (
                    [
                        "git",
                        "-C",
                        str(tmp_path),
                        "diff",
                        "--name-only",
                        "-z",
                        "--diff-filter=ACMR",
                        "HEAD",
                    ],
                ),
                {"timeout": 30},
            ),
            (
                (
                    [
                        "git",
                        "-C",
                        str(tmp_path),
                        "ls-files",
                        "--others",
                        "--exclude-standard",
                        "-z",
                    ],
                ),
                {"timeout": 30},
            ),
        ]


# ---------------------------------------------------------------------------
# Real-repo integration: each of the three unioned sources, independently
# ---------------------------------------------------------------------------


class TestUnionOfThreeSources:
    """Real git repos (no mocking) proving each source is actually unioned."""

    def test_worktree_only_unstaged_edit_is_included(
        self, tmp_path: Path, make_repo_with_base: RepoFactory
    ) -> None:
        """An edit that is neither committed nor staged -- pure worktree --
        must still show up (the ``git diff HEAD`` two-dot call, not the
        three-dot base-ref range, is what catches this)."""
        repo = make_repo_with_base(tmp_path)
        (repo / "README.md").write_text("seed\nunstaged edit\n", encoding="utf-8")

        result = _changed_paths_since_base(repo, "Test")

        assert result == ["README.md"]

    def test_staged_edit_is_included(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        (repo / "README.md").write_text("seed\nstaged edit\n", encoding="utf-8")
        git_cmd(repo, "add", "README.md")

        result = _changed_paths_since_base(repo, "Test")

        assert result == ["README.md"]

    def test_untracked_file_is_included(
        self, tmp_path: Path, make_repo_with_base: RepoFactory
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        (repo / "new_file.md").write_text("brand new\n", encoding="utf-8")

        result = _changed_paths_since_base(repo, "Test")

        assert result == ["new_file.md"]

    def test_committed_change_since_base_is_still_included(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """Regression guard: the original committed-range source still works
        once it is one of three, not the only one."""
        repo = make_repo_with_base(tmp_path)
        (repo / "committed.md").write_text("committed change\n", encoding="utf-8")
        git_cmd(repo, "add", "-A")
        git_cmd(repo, "commit", "-q", "-m", "feat: add committed file")

        result = _changed_paths_since_base(repo, "Test")

        assert result == ["committed.md"]

    def test_all_three_sources_are_unioned_without_duplicates(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        (repo / "committed.md").write_text("c\n", encoding="utf-8")
        git_cmd(repo, "add", "-A")
        git_cmd(repo, "commit", "-q", "-m", "feat: committed")
        (repo / "staged.md").write_text("s\n", encoding="utf-8")
        git_cmd(repo, "add", "staged.md")
        (repo / "README.md").write_text("seed\nunstaged\n", encoding="utf-8")
        (repo / "untracked.md").write_text("u\n", encoding="utf-8")

        result = _changed_paths_since_base(repo, "Test")

        assert result is not None
        assert set(result) == {"committed.md", "staged.md", "README.md", "untracked.md"}
        assert len(result) == len(set(result)), "must not list the same path twice"

    def test_deleted_file_is_excluded_by_acmr(
        self, tmp_path: Path, make_repo_with_base: RepoFactory
    ) -> None:
        """ACMR excludes Deleted; preserved from the pre-union implementation."""
        repo = make_repo_with_base(tmp_path)
        (repo / "README.md").unlink()

        result = _changed_paths_since_base(repo, "Test")

        assert result == []

    def test_clean_worktree_returns_empty_list(
        self, tmp_path: Path, make_repo_with_base: RepoFactory
    ) -> None:
        repo = make_repo_with_base(tmp_path)

        assert _changed_paths_since_base(repo, "Test") == []


# ---------------------------------------------------------------------------
# Rename and Unicode/space path handling (NUL-delimited output)
# ---------------------------------------------------------------------------


class TestPathEncodingEdgeCases:
    def test_pure_rename_is_reported_as_the_single_new_path(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        git_cmd(repo, "mv", "README.md", "RENAMED.md")

        result = _changed_paths_since_base(repo, "Test")

        assert result == ["RENAMED.md"]

    def test_unicode_filename_survives_intact(
        self, tmp_path: Path, make_repo_with_base: RepoFactory
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        unicode_name = "\u65e5\u672c\u8a9e.md"  # 日本語.md
        (repo / unicode_name).write_text("content\n", encoding="utf-8")

        result = _changed_paths_since_base(repo, "Test")

        assert result == [unicode_name]

    def test_filename_with_spaces_survives_intact(
        self, tmp_path: Path, make_repo_with_base: RepoFactory
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        spaced_name = "release notes.md"
        (repo / spaced_name).write_text("content\n", encoding="utf-8")

        result = _changed_paths_since_base(repo, "Test")

        assert result == [spaced_name]
