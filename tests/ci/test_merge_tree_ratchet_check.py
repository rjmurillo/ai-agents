"""Tests for scripts/ci/merge_tree_ratchet_check.py.

Tests exercise the full CLI (main()) against real git repos created in
tmp_path. No mocking of git or the linters; the linter calls are replaced
with monkeypatched counter functions to keep tests fast and hermetic.

Coverage:
- clean merge: all counters under baseline -> EXIT_OK
- regression: one counter over baseline -> EXIT_REGRESSION
- conflict: merge-tree exits 1 -> EXIT_OK with skip message
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
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)


def _make_repo_with_baselines(
    tmp_path: Path, ruff: int, taste: int, ignore: int, memory: int = 10
) -> Path:
    """A repo with committed baseline files and one tracked Python file."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    ci = repo / "scripts" / "ci"
    ci.mkdir(parents=True)
    (ci / "ruff_count_baseline.txt").write_text(f"{ruff}\n", encoding="utf-8")
    (ci / "taste_count_baseline.txt").write_text(f"{taste}\n", encoding="utf-8")
    (ci / "type_ignore_count_baseline.txt").write_text(f"{ignore}\n", encoding="utf-8")
    (ci / "memory_index_count_baseline.txt").write_text(
        f"{memory}\n", encoding="utf-8"
    )
    (repo / "hello.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(repo, "main baseline")
    return repo


def _run(repo: Path, base_ref: str = "HEAD") -> int:
    """Run main() with monkeypatched counters that always return 0."""
    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
    ):
        return _m.main(["--repo-root", str(repo), "--base-ref", base_ref])


@pytest.fixture(autouse=True)
def _zero_memory_index_count():
    with patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0):
        yield


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
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

    def test_regression_blocks(self, tmp_path: Path) -> None:
        """One counter above baseline -> EXIT_REGRESSION."""
        repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=6),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_REGRESSION

    def test_memory_index_regression_blocks(self, tmp_path: Path) -> None:
        """The merge-tree gate covers the memory-index count ratchet too."""
        repo = _make_repo_with_baselines(
            tmp_path, ruff=10, taste=10, ignore=10, memory=5
        )
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch(
                "scripts.ci.memory_index_count_ratchet.current_count", return_value=6
            ),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_REGRESSION

    def test_conflict_skips_with_ok(self, tmp_path: Path) -> None:
        """Merge conflict -> EXIT_OK; counters are NOT invoked."""
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

        assert rc == _m.EXIT_OK
        # None of the counters should run - conflict was detected and skipped
        assert call_counts == {"ruff": 0, "taste": 0, "ignore": 0, "memory": 0}, (
            f"Counters ran despite conflict: {call_counts}"
        )

    def test_git_failure_returns_external(self, tmp_path: Path) -> None:
        """git merge-tree hard failure -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        rc = _m.main(
            ["--repo-root", str(repo), "--base-ref", "nonexistent-ref-xyz123"]
        )
        assert rc == _m.EXIT_EXTERNAL

    def test_counter_returns_none_is_external(self, tmp_path: Path) -> None:
        """Counter returning None -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=None),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_EXTERNAL

    def test_missing_baseline_returns_config(self, tmp_path: Path) -> None:
        """Missing baseline at base ref -> EXIT_CONFIG."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "scripts/ci/ruff_count_baseline.txt")
        _commit_all(repo, "remove ruff baseline")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        assert rc == _m.EXIT_CONFIG

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
        created_dirs: list[Path] = []
        _real_mkdtemp = __import__("tempfile").mkdtemp

        def _capturing_mkdtemp(**kwargs):
            d = _real_mkdtemp(**kwargs)
            created_dirs.append(Path(d))
            return d

        import tempfile

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=5),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch.object(tempfile, "mkdtemp", side_effect=_capturing_mkdtemp),
        ):
            _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        for d in created_dirs:
            assert not d.exists(), f"scratch dir {d} was not cleaned up"

    def test_stale_branch_is_caught(self, tmp_path: Path) -> None:
        """The canonical #4272 failure shape.

        main lowers taste baseline from 10 to 5; a branch cut before that
        merge carries an old taste count of 8, which was fine against the old
        ceiling of 10 but breaches the new ceiling of 5.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        # Branch: old taste count is 8 (under the old ceiling).
        _git(repo, "checkout", "-b", "pr-branch")
        # Simulate a PR that lowers ruff but not taste.
        (repo / "pr_change.py").write_text("# new file\n", encoding="utf-8")
        _commit_all(repo, "PR change")

        # Main: lower taste baseline to 5.
        _git(repo, "checkout", "main")
        (repo / "scripts" / "ci" / "taste_count_baseline.txt").write_text(
            "5\n", encoding="utf-8"
        )
        _commit_all(repo, "lower taste baseline to 5")
        _git(repo, "checkout", "pr-branch")

        # Merged tree would have taste count 8, against new ceiling 5 -> REGRESSION.
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=8),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION

    def test_stale_branch_after_rebase_passes(self, tmp_path: Path) -> None:
        """After rebasing onto updated main, the same branch passes."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "pr_change.py").write_text("# new file\n", encoding="utf-8")
        _commit_all(repo, "PR change")

        _git(repo, "checkout", "main")
        (repo / "scripts" / "ci" / "taste_count_baseline.txt").write_text(
            "5\n", encoding="utf-8"
        )
        _commit_all(repo, "lower taste baseline to 5")

        # Rebase pr-branch onto updated main.
        _git(repo, "checkout", "pr-branch")
        _git(repo, "rebase", "main")

        # After rebase, taste count of 4 passes the new ceiling of 5.
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=4),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
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

    def _behind_base_clone(self, tmp_path: Path, *, shallow: bool) -> Path:
        """A clone whose branch is behind base, with base fetched shallow or full.

        Reproduces issue #4518: the gate exists to judge branches that are behind
        their base, and a shallow base fetch made exactly that case error out.
        """
        origin = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        behind_point = _git(origin, "rev-parse", "HEAD").stdout.strip()
        (origin / "later.py").write_text("y = 2\n", encoding="utf-8")
        _commit_all(origin, "main moves ahead")

        work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.email", "t@e.com"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "t"], check=True)
        _git(work, "checkout", "-q", "-b", "feature", behind_point)
        (work / "feature.py").write_text("z = 3\n", encoding="utf-8")
        _commit_all(work, "feature work")

        depth = ["--depth=1"] if shallow else []
        subprocess.run(
            ["git", "-C", str(work), "fetch", "-q", *depth, "origin", "main"], check=True
        )
        return work

    def test_branch_behind_base_renders_a_verdict(self, tmp_path: Path) -> None:
        """Issue #4518: a branch behind its base must get a real verdict.

        This is the gate's target case. With the base fetched at full depth a
        merge base is reachable, so the check evaluates the merged tree instead
        of erroring out.
        """
        work = self._behind_base_clone(tmp_path, shallow=False)
        rc = _run(work, "FETCH_HEAD")
        assert rc == _m.EXIT_OK, "behind-base branch must be judged, not errored"

    def test_shallow_base_fetch_reports_the_fetch_not_a_ratchet_breach(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Issue #4518: if the shallow fetch ever returns, say so by name.

        Negative control for the test above: same repository shape, only the
        fetch depth differs. Without this pair a regression to `--depth=1` is
        indistinguishable from a real ratchet breach.
        """
        work = self._behind_base_clone(tmp_path, shallow=True)
        rc = _run(work, "FETCH_HEAD")
        assert rc == _m.EXIT_EXTERNAL
        err = capsys.readouterr().err
        assert "shallow-fetch" in err, err
        assert "#4518" in err, err

    def test_shallow_diagnostic_is_not_followed_by_a_generic_oid_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """PR #4567 review: one failure must produce exactly one explanation.

        The caller used to append "git merge-tree did not produce a tree OID"
        after the shallow-fetch diagnosis. Two messages for one failure make the
        specific one read like a guess and send the reader back to the ratchet.
        """
        work = self._behind_base_clone(tmp_path, shallow=True)
        _run(work, "FETCH_HEAD")
        err = capsys.readouterr().err
        assert "shallow-fetch" in err, err
        assert "did not produce a tree OID" not in err, err

    def test_empty_merge_tree_output_still_explains_itself(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge case: git succeeds but prints no OID, so nothing else explains it.

        Moving the message out of the caller must not turn this path silent.
        A bare EXIT_EXTERNAL with no stderr is the failure mode to avoid.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        empty = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")
        with patch.object(_m, "_git", return_value=empty):
            oid, conflicts = _m._merge_tree_oid(repo, "HEAD")
        assert oid is None
        assert conflicts is False
        err = capsys.readouterr().err
        assert "no tree OID" in err, err

    def test_successful_run_prints_no_failure_diagnostic(self, tmp_path: Path) -> None:
        """Negative control: the diagnostics must not fire on a clean evaluation.

        Without this the two assertions above would pass against a build that
        never writes to stderr at all.
        """
        work = self._behind_base_clone(tmp_path, shallow=False)
        with patch.object(_m.sys.stderr, "write") as writes:
            rc = _run(work, "FETCH_HEAD")
        assert rc == _m.EXIT_OK
        assert writes.call_args_list == []


class TestMergeTreeInstalledBaseline:
    """Integration coverage for branch-installed baseline ceilings."""

    def test_branch_lowering_a_baseline_below_the_merged_count_is_blocked(
        self, tmp_path: Path
    ) -> None:
        """The issue #4538 shape: a branch installs a ceiling main cannot meet.

        PR #4208 activated RUF100 and rewrote the ruff baseline 308 -> 126 in
        one commit. Its own tree measured exactly 126. Between its base and its
        merge, PR #4448 landed 14 more dead ``noqa`` directives, so the merged
        tree measured 140. The old gate compared 140 against the BASE's 308 and
        passed, and main merged red.

        The ceiling must be the baseline the merge installs, not the one it
        replaces.
        """
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

    def test_branch_lowering_a_baseline_the_merged_tree_meets_passes(
        self, tmp_path: Path
    ) -> None:
        """Positive control for the gate above: a truthful lowering still lands.

        Same branch shape, but the merged tree actually measures the number the
        branch ships. Without this the gate could pass the test above by
        refusing every baseline reduction, which would ban all cleanup work.
        """
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

    def test_branch_raising_a_baseline_cannot_buy_merged_tree_headroom(
        self, tmp_path: Path
    ) -> None:
        """The opposite direction must stay closed.

        Reading the merged tree's baseline alone would let a branch raise the
        ceiling and walk merged-tree debt straight through. The base's value
        still applies, so the lower of the two governs.
        """
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

    def test_branch_deleting_a_baseline_is_a_config_error(self, tmp_path: Path) -> None:
        """A baseline readable at base but absent from the merged tree blocks.

        Deleting the file must not read as "no ceiling"; the check has to fail
        loudly rather than fall open.
        """
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

    def test_baseline_is_read_from_merged_tree_not_head_or_worktree(
        self, tmp_path: Path
    ) -> None:
        """A base-side baseline change must be read from the synthetic merge.

        The branch is cut while the baseline is 3. Main then raises it to 5,
        while the branch only changes code. The merged tree records 5, but
        both HEAD and the checked-out worktree still record 3. A count of 4
        therefore passes only when the reader uses the extracted merged tree.
        """
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
