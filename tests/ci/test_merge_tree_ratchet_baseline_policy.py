"""Integration tests for merge-tree baseline policy (issue #4538)."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import cli_exit_contract_ratchet as _cli_exit
from scripts.ci import memory_index_count_ratchet as _memory_index
from scripts.ci import merge_tree_ratchet_check as _m
from tests.ci.test_merge_tree_ratchet_check import (
    _branch_with_counts,
    _commit_all,
    _git,
    _make_repo_with_baselines,
    _tree_counters,
    _write_count,
)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_memory_index_counter_reads_synthetic_merged_tree_not_worktree(
    tmp_path: Path,
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10, memory=10)
    _git(repo, "checkout", "-b", "pr-branch")
    (repo / "branch.py").write_text("branch = True\n", encoding="utf-8")
    _commit_all(repo, "branch change")

    _git(repo, "checkout", "main")
    merged_only = Path("merged-only.txt")
    (repo / merged_only).write_text("from target branch\n", encoding="utf-8")
    _commit_all(repo, "target branch change")
    _git(repo, "checkout", "pr-branch")

    roots: list[Path] = []
    contents: list[str] = []

    def collect_from_synthetic_tree(scratch_root: Path) -> list[str]:
        roots.append(scratch_root)
        contents.append((scratch_root / merged_only).read_text(encoding="utf-8"))
        return []

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch.object(_memory_index, "_collect", side_effect=collect_from_synthetic_tree),
        patch.object(
            _memory_index,
            "current_count",
            wraps=_memory_index.current_count,
        ) as memory_counter,
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

    assert rc == _m.EXIT_OK
    # Merged tree first, then the base tip: two scratch trees, never the worktree.
    assert memory_counter.call_count == 2
    assert [c.args[0] for c in memory_counter.call_args_list] == roots
    assert repo not in roots
    assert roots[0] != roots[1]
    assert contents[0] == "from target branch\n"
    assert not (repo / merged_only).exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cli_exit_counter_receives_materialized_merged_tree(tmp_path: Path) -> None:
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
    assert cli_counter.call_args.args[0] != repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestBaseDerivedPolicy:
    """Ruff, taste, type-ignore and memory-index keep no scalar (issue #5363)."""

    def test_branch_lowering_the_count_passes(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=308, taste=10, ignore=10)
        _branch_with_counts(repo, ruff=126)
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_OK

    def test_branch_raising_the_count_is_blocked(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No scalar exists to raise, so the only lever is the count itself."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _branch_with_counts(repo, ruff=50)
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION
        assert "REGRESSION. 50 > 10 at the base ref (+40)" in capsys.readouterr().err

    def test_base_tip_lowered_after_fork_tightens_the_ceiling(self, tmp_path: Path) -> None:
        """main drops to 5 after the fork; the branch stays at 10 through a new file."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _branch_with_counts(repo, **{"ruff-branch": 2})
        _git(repo, "checkout", "-q", "main")
        _write_count(repo, "ruff", 5)
        _commit_all(repo, "main lowers ruff to 5")
        _git(repo, "checkout", "-q", "pr-branch")
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION

    def test_bootstrap_when_base_lacks_the_script(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "-q", "scripts/ci/ruff_count_ratchet.py")
        _commit_all(repo, "base predates the ruff ratchet")
        _branch_with_counts(repo, ruff=500)
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_OK
        assert "bootstrap" in capsys.readouterr().out

    def test_bootstrap_is_per_ratchet(self, tmp_path: Path) -> None:
        """Negative control: a missing ruff script does not excuse a taste breach."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "-q", "scripts/ci/ruff_count_ratchet.py")
        _commit_all(repo, "base predates the ruff ratchet")
        _branch_with_counts(repo, taste=11)
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestCliExitScalarPolicy:
    """The cli exit contract ratchet keeps min(base, merged) scalar semantics."""

    @staticmethod
    def _run_with_cli_count(repo: Path, count: int) -> int:
        with _tree_counters(cli=count):
            return _m.main(["--repo-root", str(repo), "--base-ref", "main"])

    @staticmethod
    def _write_cli_baseline(repo: Path, value: int) -> None:
        (repo / "scripts" / "ci" / "cli_exit_contract_baseline.txt").write_text(
            f"{value}\n", encoding="utf-8"
        )

    def test_branch_lowering_below_merged_count_is_blocked(self, tmp_path: Path) -> None:
        """A branch cannot install a ceiling the merged tree does not meet."""
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0, cli=308)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        self._write_cli_baseline(repo, 126)
        _commit_all(repo, "lower the cli exit baseline to 126")
        assert self._run_with_cli_count(repo, 140) == _m.EXIT_REGRESSION

    def test_truthful_baseline_lowering_passes(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0, cli=308)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        self._write_cli_baseline(repo, 126)
        _commit_all(repo, "lower the cli exit baseline to 126")
        assert self._run_with_cli_count(repo, 126) == _m.EXIT_OK

    def test_branch_raising_baseline_cannot_buy_headroom(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0, cli=10)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        self._write_cli_baseline(repo, 100)
        _commit_all(repo, "raise the cli exit baseline to 100")
        assert self._run_with_cli_count(repo, 50) == _m.EXIT_REGRESSION

    def test_branch_deleting_baseline_is_config_error(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        _git(repo, "rm", "-q", "scripts/ci/cli_exit_contract_baseline.txt")
        _commit_all(repo, "delete the cli exit baseline")
        assert self._run_with_cli_count(repo, 0) == _m.EXIT_CONFIG

    def test_branch_can_add_new_baseline_atomically(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0)
        _git(repo, "rm", "-q", "scripts/ci/cli_exit_contract_baseline.txt")
        _commit_all(repo, "base has no cli exit baseline")
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        self._write_cli_baseline(repo, 5)
        _commit_all(repo, "add cli exit ratchet baseline")
        assert self._run_with_cli_count(repo, 5) == _m.EXIT_OK

    def test_baseline_is_read_from_merged_tree_not_head_or_worktree(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0, cli=3)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        (repo / "pr_change.py").write_text("# branch-only change\n", encoding="utf-8")
        _commit_all(repo, "branch code change")
        _git(repo, "checkout", "-q", "main")
        self._write_cli_baseline(repo, 5)
        _commit_all(repo, "raise cli exit baseline on main")
        _git(repo, "checkout", "-q", "pr-branch")
        assert self._run_with_cli_count(repo, 4) == _m.EXIT_OK

    def test_count_above_the_main_baseline_is_blocked(self, tmp_path: Path) -> None:
        """Negative control for the test above: 6 > 5 must fail."""
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=0, ignore=0, cli=3)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        (repo / "pr_change.py").write_text("# branch-only change\n", encoding="utf-8")
        _commit_all(repo, "branch code change")
        _git(repo, "checkout", "-q", "main")
        self._write_cli_baseline(repo, 5)
        _commit_all(repo, "raise cli exit baseline on main")
        _git(repo, "checkout", "-q", "pr-branch")
        assert self._run_with_cli_count(repo, 6) == _m.EXIT_REGRESSION
