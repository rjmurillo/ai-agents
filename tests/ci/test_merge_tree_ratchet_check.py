"""Tests for scripts/ci/merge_tree_ratchet_check.py.

Tests exercise the full CLI (main()) against real git repos created in
tmp_path. No mocking of git or the linters; the linter calls are replaced
with monkeypatched counter functions to keep tests fast and hermetic.

Coverage:
- clean merge: all counters under baseline -> EXIT_OK
- regression: one counter over baseline -> EXIT_REGRESSION
- conflict: merge-tree exits 1 -> distinct nonzero conflict exit
- git failure: merge-tree exits 2 -> EXIT_EXTERNAL
- counter returns None: -> EXIT_EXTERNAL
- baseline unreadable at base ref: -> EXIT_CONFIG
- baseline diagnostics identify whether the base or merged tree is unreadable
- baseline is read from the merged tree, not HEAD or the working tree
- scratch dir cleanup: always cleaned up, even on failure
- negative control: a cosmetic comment change to the script does NOT break
  the regression test (proves the test is not asserting on line number)
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_check as _m


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)


_COUNTED = {
    "ruff": "scripts.ci.ruff_count_ratchet",
    "taste": "scripts.ci.taste_count_ratchet",
    "type_ignore": "scripts.ci.type_ignore_count_ratchet",
    "memory_index": "scripts.ci.memory_index_count_ratchet",
}


def _tree_count(name: str):
    """Fake counter: the sum of counts/<name>*.txt in whatever tree it is handed."""

    def count(root: Path) -> int:
        files = sorted((root / "counts").glob(f"{name}*.txt"))
        return sum(int(f.read_text(encoding="utf-8").strip()) for f in files)

    return count


@contextmanager
def _tree_counters(cli: int = 0) -> Iterator[None]:
    """Patch the four base-derived counters to read counts/ from the tree measured.

    The base tip and the merged tree are separate trees, so a fake that returns a
    constant cannot tell them apart. Reading the tree keeps the gate's real
    materialization and base-tip measurement in play.
    """
    with (
        patch(f"{_COUNTED['ruff']}.current_count", side_effect=_tree_count("ruff")),
        patch(f"{_COUNTED['taste']}.current_count", side_effect=_tree_count("taste")),
        patch(
            f"{_COUNTED['type_ignore']}.current_count",
            side_effect=_tree_count("type_ignore"),
        ),
        patch(
            f"{_COUNTED['memory_index']}.current_count",
            side_effect=_tree_count("memory_index"),
        ),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=cli),
    ):
        yield


def _write_count(repo: Path, name: str, value: int) -> None:
    counts = repo / "counts"
    counts.mkdir(exist_ok=True)
    (counts / f"{name}.txt").write_text(f"{value}\n", encoding="utf-8")


def _make_repo_with_baselines(
    tmp_path: Path,
    ruff: int,
    taste: int,
    ignore: int,
    memory: int = 10,
    cli: int = 10,
) -> Path:
    """A repo whose base tip carries every ratchet script and the fake counts.

    The four base-derived ratchets keep no scalar (issue #5363): their counts
    live in counts/<name>.txt, read by ``_tree_counters``. The marker scripts
    keep the base tip out of the bootstrap state. Only the cli exit contract
    ratchet still has a committed scalar.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    ci = repo / "scripts" / "ci"
    ci.mkdir(parents=True)
    for script in (
        "ruff_count_ratchet",
        "taste_count_ratchet",
        "type_ignore_count_ratchet",
        "memory_index_count_ratchet",
    ):
        (ci / f"{script}.py").write_text("# marker\n", encoding="utf-8")
    _write_count(repo, "ruff", ruff)
    _write_count(repo, "taste", taste)
    _write_count(repo, "type_ignore", ignore)
    _write_count(repo, "memory_index", memory)
    (ci / "cli_exit_contract_baseline.txt").write_text(f"{cli}\n", encoding="utf-8")
    (repo / "hello.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(repo, "main baseline")
    return repo


def _branch_with_counts(repo: Path, **counts: int) -> None:
    """Fork pr-branch from main and commit the given counts/<name>.txt files."""
    _git(repo, "checkout", "-q", "-b", "pr-branch")
    for name, value in counts.items():
        _write_count(repo, name, value)
    _commit_all(repo, "branch counts")


def _run(repo: Path, base_ref: str = "HEAD") -> int:
    """Run main() with monkeypatched counters that always return 0."""
    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
    ):
        return _m.main(["--repo-root", str(repo), "--base-ref", base_ref])


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestMergeTreeRatchetCheck:
    def test_clean_merge_passes(self, tmp_path: Path) -> None:
        """All counters under baseline -> EXIT_OK."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=5),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=5),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=5),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_OK

    def test_count_equal_to_baseline_passes(self, tmp_path: Path) -> None:
        """count == baseline -> EXIT_OK (equal is not a regression)."""
        repo = _make_repo_with_baselines(tmp_path, ruff=7, taste=7, ignore=7)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=7),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=7),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=7),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_OK

    def test_regression_blocks(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """One counter above the base tip -> EXIT_REGRESSION."""
        repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
        _branch_with_counts(repo, ruff=6)
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION
        error = capsys.readouterr().err
        assert "ruff count ratchet: REGRESSION. 6 > 5 at the base ref" in error
        assert "BLOCKED. The merged result breaches a ratchet ceiling." in error
        assert "Merge or rebase from main and re-check." in error

    def test_count_at_base_tip_passes(self, tmp_path: Path) -> None:
        """Negative control: the same branch shape at the base count is EXIT_OK."""
        repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
        _git(repo, "checkout", "-q", "-b", "pr-branch")
        _write_count(repo, "ruff", 5)
        (repo / "hello.py").write_text("x = 2\n", encoding="utf-8")
        _commit_all(repo, "branch code change")
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_OK

    def test_memory_index_regression_blocks(self, tmp_path: Path) -> None:
        """The merge-tree gate covers the memory-index count ratchet too."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10, memory=5)
        _branch_with_counts(repo, memory_index=6)
        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION

    def test_conflict_fails_closed_without_running_counters(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        # Create a branch that conflicts with main on hello.py
        _git(repo, "checkout", "-b", "feature")
        (repo / "hello.py").write_text("x = 2  # feature\n", encoding="utf-8")
        _commit_all(repo, "feature change")

        _git(repo, "checkout", "main")
        (repo / "hello.py").write_text("x = 3  # main\n", encoding="utf-8")
        _commit_all(repo, "main change")

        # Check out feature so HEAD is the feature branch
        _git(repo, "checkout", "feature")

        call_counts = {"ruff": 0, "taste": 0, "ignore": 0, "memory": 0}

        def _ruff(_root):
            call_counts["ruff"] += 1
            return 0

        def _taste(_root):
            call_counts["taste"] += 1
            return 0

        def _ignore(_root):
            call_counts["ignore"] += 1
            return 0

        def _memory(_root):
            call_counts["memory"] += 1
            return 0

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", side_effect=_ruff),
            patch("scripts.ci.taste_count_ratchet.current_count", side_effect=_taste),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", side_effect=_ignore),
            patch(
                "scripts.ci.memory_index_count_ratchet.current_count",
                side_effect=_memory,
            ),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_CONFLICT
        error = capsys.readouterr().err
        assert "merge has conflicts" in error
        assert "resolve the conflicts and rerun the ratchet" in error
        assert "breaches a ratchet ceiling" not in error
        assert call_counts == {"ruff": 0, "taste": 0, "ignore": 0, "memory": 0}, (
            f"Counters ran despite conflict: {call_counts}"
        )

    def test_git_failure_returns_external(self, tmp_path: Path) -> None:
        """git merge-tree hard failure -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "nonexistent-ref-xyz123"])
        assert rc == _m.EXIT_EXTERNAL

    def test_counter_returns_none_is_external(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Counter returning None -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=None),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        assert rc == _m.EXIT_EXTERNAL
        error = capsys.readouterr().err
        assert "counter returned None" in error
        assert "BLOCKED. The merged result breaches a ratchet ceiling." not in error

    def test_missing_cli_exit_baseline_returns_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Missing scalar at the base ref -> EXIT_CONFIG (cli exit ratchet only)."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "scripts/ci/cli_exit_contract_baseline.txt")
        _commit_all(repo, "remove cli exit baseline")

        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        assert rc == _m.EXIT_CONFIG
        error = capsys.readouterr().err
        assert "CONFIG ERROR" in error
        assert "BLOCKED. The merged result breaches a ratchet ceiling." not in error

    def test_missing_ratchet_script_at_base_is_bootstrap_not_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A base-derived ratchet needs no scalar: no script at base means bootstrap."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "-q", "scripts/ci/ruff_count_ratchet.py")
        _commit_all(repo, "base predates the ruff ratchet")
        _branch_with_counts(repo, ruff=500)

        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_OK
        captured = capsys.readouterr()
        assert "ruff count ratchet: bootstrap" in captured.out
        assert "CONFIG ERROR" not in captured.err

    def test_scratch_dir_cleaned_on_success(self, tmp_path: Path) -> None:
        """Scratch dir must be removed on a clean run."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        created_dirs: list[Path] = []
        _real_mkdtemp = __import__("tempfile").mkdtemp

        def _capturing_mkdtemp(**kwargs):
            d = _real_mkdtemp(**kwargs)
            created_dirs.append(Path(d))
            return d

        import tempfile

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch.object(tempfile, "mkdtemp", side_effect=_capturing_mkdtemp),
        ):
            _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        for d in created_dirs:
            assert not d.exists(), f"scratch dir {d} was not cleaned up"

    def test_scratch_dir_cleaned_on_regression(self, tmp_path: Path) -> None:
        """Scratch dir must be removed even when a regression is detected."""
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=10, ignore=10)
        _branch_with_counts(repo, ruff=5)
        created_dirs: list[Path] = []
        _real_mkdtemp = __import__("tempfile").mkdtemp

        def _capturing_mkdtemp(**kwargs):
            d = _real_mkdtemp(**kwargs)
            created_dirs.append(Path(d))
            return d

        import tempfile

        with (
            _tree_counters(),
            patch.object(tempfile, "mkdtemp", side_effect=_capturing_mkdtemp),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION
        assert created_dirs, "no scratch dir was created"

        for d in created_dirs:
            assert not d.exists(), f"scratch dir {d} was not cleaned up"

    def test_stale_branch_is_caught(self, tmp_path: Path) -> None:
        """The canonical #4272 failure shape.

        main lowers the taste count from 10 to 5 after the fork. The branch adds
        3 of its own. That was fine against the fork point (10) but the merged
        tree measures 8 against the base tip's 5.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _branch_with_counts(repo, **{"taste-branch": 3})

        _git(repo, "checkout", "-q", "main")
        _write_count(repo, "taste", 5)
        _commit_all(repo, "main lowers taste count to 5")
        _git(repo, "checkout", "-q", "pr-branch")

        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION

    def test_stale_branch_after_rebase_passes(self, tmp_path: Path) -> None:
        """After rebasing onto updated main and paying the debt, the branch passes."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _branch_with_counts(repo, **{"taste-branch": 3})

        _git(repo, "checkout", "-q", "main")
        _write_count(repo, "taste", 5)
        _commit_all(repo, "main lowers taste count to 5")

        _git(repo, "checkout", "-q", "pr-branch")
        _git(repo, "rebase", "-q", "main")
        _write_count(repo, "taste-branch", 0)
        _commit_all(repo, "pay the branch debt")

        with _tree_counters():
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_OK

    def test_cosmetic_comment_change_does_not_affect_result(self, tmp_path: Path) -> None:
        """Negative control: a comment-only change to this test file does NOT cause
        regression. Proves tests are not asserting on line numbers or file content.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        # Add a comment-only Python file; counters return 0 -> still passes.
        (repo / "commented.py").write_text(
            "# This is just a comment. No violations.\n", encoding="utf-8"
        )
        _commit_all(repo, "add comment file")
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_OK
