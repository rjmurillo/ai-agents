"""Integration tests for merge-tree baseline policy (issue #4538)."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import cli_exit_contract_ratchet as _cli_exit
from scripts.ci import memory_index_count_ratchet as _memory_index
from scripts.ci import merge_tree_ratchet_check as _m
from tests.ci.test_merge_tree_ratchet_check import (
    _commit_all,
    _git,
    _make_repo_with_baselines,
)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_memory_index_counter_reads_synthetic_merged_tree_not_worktree(
    tmp_path: Path,
) -> None:
    repo = _make_repo_with_baselines(
        tmp_path, ruff=10, taste=10, ignore=10, memory=10
    )
    _git(repo, "checkout", "-b", "pr-branch")
    (repo / "branch.py").write_text("branch = True\n", encoding="utf-8")
    _commit_all(repo, "branch change")

    _git(repo, "checkout", "main")
    merged_only = Path("merged-only.txt")
    (repo / merged_only).write_text("from target branch\n", encoding="utf-8")
    _commit_all(repo, "target branch change")
    _git(repo, "checkout", "pr-branch")

    observed: dict[str, Path | str] = {}

    def collect_from_synthetic_tree(scratch_root: Path) -> list[str]:
        observed["root"] = scratch_root
        observed["content"] = (scratch_root / merged_only).read_text(encoding="utf-8")
        return []

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch.object(
            _memory_index, "_collect", side_effect=collect_from_synthetic_tree
        ),
        patch.object(
            _memory_index,
            "current_count",
            wraps=_memory_index.current_count,
        ) as memory_counter,
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

    assert rc == _m.EXIT_OK
    memory_counter.assert_called_once()
    scratch_root = memory_counter.call_args.args[0]
    assert scratch_root == observed["root"]
    assert scratch_root != repo
    assert observed["content"] == "from target branch\n"
    assert not (repo / merged_only).exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cli_exit_counter_receives_materialized_merged_tree(tmp_path: Path) -> None:
    """A genuinely diverged branch still counts against a materialized copy.

    ``main`` commits ``diverged-only.txt`` after the branch point, so
    ``is_fast_forward_clean`` (issue #5441) is False here and the check must
    still fall back to materialize-and-recount: this is the scenario that
    protects issue #4398 (a branch behind a base ref that lowered a
    baseline), and it must never silently read the live working tree.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    _git(repo, "checkout", "-b", "pr-branch")
    (repo / "branch.py").write_text("branch = True\n", encoding="utf-8")
    _commit_all(repo, "branch change")
    _git(repo, "checkout", "main")
    (repo / "diverged-only.txt").write_text("main moved on\n", encoding="utf-8")
    _commit_all(repo, "main diverges")
    _git(repo, "checkout", "pr-branch")

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch.object(
            _cli_exit,
            "current_count",
            wraps=_cli_exit.current_count,
        ) as cli_counter,
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

    assert rc == _m.EXIT_OK
    cli_counter.assert_called_once()
    assert cli_counter.call_args.args[0] != repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_fast_forward_clean_reuses_working_tree_without_materializing(
    tmp_path: Path,
) -> None:
    """A clean fast-forward branch counts straight off repo_root (issue #5441).

    This is the dedup this issue asks for: when the merge is provably a
    no-op, materializing a scratch copy just to recount a value repo_root
    already holds is wasted work, so the counter must run against repo_root
    directly instead.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch.object(
            _cli_exit,
            "current_count",
            wraps=_cli_exit.current_count,
        ) as cli_counter,
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

    assert rc == _m.EXIT_OK
    cli_counter.assert_called_once()
    assert cli_counter.call_args.args[0] == repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestMergeTreeBaselinePolicy:
    def test_branch_lowering_below_merged_count_is_blocked(
        self, tmp_path: Path
    ) -> None:
        """A branch cannot install a ceiling the merged tree does not meet."""
        repo = _make_repo_with_baselines(tmp_path, ruff=308, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "ruff_count_baseline.txt").write_text(
            "126\n", encoding="utf-8"
        )
        _commit_all(repo, "activate RUF100 and lower the ruff baseline to 126")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=140),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION

    def test_truthful_baseline_lowering_passes(self, tmp_path: Path) -> None:
        """A baseline reduction still lands when the merged tree meets it."""
        repo = _make_repo_with_baselines(tmp_path, ruff=308, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "ruff_count_baseline.txt").write_text(
            "126\n", encoding="utf-8"
        )
        _commit_all(repo, "lower the ruff baseline to 126")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=126),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_OK

    def test_branch_raising_baseline_cannot_buy_headroom(
        self, tmp_path: Path
    ) -> None:
        """The base value still blocks debt hidden by a raised baseline."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "ruff_count_baseline.txt").write_text(
            "100\n", encoding="utf-8"
        )
        _commit_all(repo, "raise the ruff baseline to 100")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=50),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION

    def test_branch_deleting_baseline_is_config_error(self, tmp_path: Path) -> None:
        """A baseline absent from the merged tree fails closed."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        _git(repo, "rm", "-q", "scripts/ci/ruff_count_baseline.txt")
        _commit_all(repo, "delete the ruff baseline")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_CONFIG

    def test_branch_can_add_new_baseline_atomically(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "-q", "scripts/ci/cli_exit_contract_baseline.txt")
        _commit_all(repo, "base has no cli exit baseline")

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "cli_exit_contract_baseline.txt").write_text(
            "5\n", encoding="utf-8"
        )
        _commit_all(repo, "add cli exit ratchet baseline")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch(
                "scripts.ci.cli_exit_contract_ratchet.current_count", return_value=5
            ),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_OK

    def test_baseline_is_read_from_merged_tree_not_head_or_worktree(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=3, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "pr_change.py").write_text("# branch-only change\n", encoding="utf-8")
        _commit_all(repo, "branch code change")

        _git(repo, "checkout", "main")
        (repo / "scripts" / "ci" / "ruff_count_baseline.txt").write_text(
            "5\n", encoding="utf-8"
        )
        _commit_all(repo, "raise ruff baseline on main")
        _git(repo, "checkout", "pr-branch")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=4),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_OK
