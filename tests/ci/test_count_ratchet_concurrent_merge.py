"""The concurrent-lowering race and the gate that blocks it (issue #4057).

Two branches can each remove one violation and write the same lowered
baseline. Git merges the identical one-line edits without a conflict, so the
merged tree has improved twice while the file fell once, and the default
branch goes red on a check that both branches passed.

These run against real git because the merge itself is the subject: a
stand-in that matched on the subcommand would report a clean merge no matter
what the two branches wrote.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from tests.ci.count_ratchet_git_harness import (
    checkout,
    commit_all,
    git,
    init_repo,
    run_ratchet,
)


def marker_counter(repo: Path):
    """Count the marker files still on disk. Stands in for a linter scan."""

    def _count(_root: Path) -> int:
        return len(list(repo.glob("violation_*.txt")))

    return _count


def repo_with_markers(tmp_path: Path, count: int) -> tuple[Path, Path]:
    """A repository holding ``count`` markers and a baseline that matches."""
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    for index in range(count):
        (repo / f"violation_{index}.txt").write_text("x\n", encoding="utf-8")
    baseline = repo / "base.txt"
    baseline.write_text(f"{count}\n", encoding="utf-8")
    commit_all(repo, f"seed {count}")
    return repo, baseline


def lower_on_branch(repo: Path, baseline: Path, name: str, marker: int, to: int) -> int:
    """Cut ``name`` from main, drop one marker, record ``to``, and check it."""
    checkout(repo, "main")
    checkout(repo, "-b", name)
    (repo / f"violation_{marker}.txt").unlink()
    baseline.write_text(f"{to}\n", encoding="utf-8")
    commit_all(repo, f"{name}: lower to {to}")
    return run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")


def merge_into_main(repo: Path, branch: str) -> None:
    """Land ``branch`` on main, failing the test if git refuses the merge."""
    checkout(repo, "main")
    merge = git(repo, "merge", "--no-ff", "-q", "-m", f"merge {branch}", branch)
    assert merge.returncode == 0, merge.stderr


def bring_up_to_date(repo: Path, branch: str) -> None:
    """Merge main into ``branch``, which is what an up-to-date policy forces."""
    checkout(repo, branch)
    merge = git(repo, "merge", "--no-ff", "-q", "-m", "sync main", "main")
    assert merge.returncode == 0, merge.stderr


def two_branches_that_each_lower_by_one(tmp_path: Path) -> tuple[Path, Path]:
    """Both branches pass their own leg. That is what makes the race reachable."""
    repo, baseline = repo_with_markers(tmp_path, 2)
    assert lower_on_branch(repo, baseline, "branch-a", 0, 1) == count_ratchet.EXIT_OK
    assert lower_on_branch(repo, baseline, "branch-b", 1, 1) == count_ratchet.EXIT_OK
    return repo, baseline


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_two_concurrent_baseline_lowerings_leave_the_merged_tree_stale(
    tmp_path, capsys
):
    """Both branches pass, the identical edits merge clean, and main goes red.

    This is the race issue #4057 reports. Each branch removes one violation
    and writes the same lowered value, so git sees no conflict, but the merged
    tree has improved twice while the baseline fell once.
    """
    repo, baseline = two_branches_that_each_lower_by_one(tmp_path)

    for branch in ("branch-a", "branch-b"):
        merge_into_main(repo, branch)

    assert count_ratchet.read_baseline(baseline) == 1
    assert marker_counter(repo)(repo) == 0
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo))

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BASELINE STALE. 0 violations < baseline 1 (-1)" in err
    assert "merged without conflict" in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_requiring_a_current_base_turns_the_second_branch_red_before_it_merges(
    tmp_path, capsys
):
    """The enforcement point for issue #4057, proven end to end.

    The chosen gate is the strict required-status-checks policy on the default
    branch: the second branch cannot merge until it is current with main, and
    updating it re-runs this ratchet. The race above only lands because
    branch-b merges on a verdict taken before branch-a landed. Bring branch-b
    up to date and the same verdict flips to a blocking exit, so the stale
    merge never reaches main. The decision and the rejected alternatives are
    recorded in ``.github/AGENTS.md``.
    """
    repo, baseline = two_branches_that_each_lower_by_one(tmp_path)
    merge_into_main(repo, "branch-a")

    bring_up_to_date(repo, "branch-b")
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE STALE. 0 violations < baseline 1 (-1)" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_updated_second_branch_goes_green_once_it_records_the_true_count(
    tmp_path, capsys
):
    """The gate is escapable through the documented remedy, not a wedge.

    A blocking check that no commit can clear would trade a red main for a
    stuck queue. The baseline-only commit the failure text asks for is the way
    out, and it has to work.
    """
    repo, baseline = two_branches_that_each_lower_by_one(tmp_path)
    merge_into_main(repo, "branch-a")

    bring_up_to_date(repo, "branch-b")
    baseline.write_text("0\n", encoding="utf-8")
    commit_all(repo, "record the true count")
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_OK
    assert "OK (count == baseline 0)" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cumulative_lowering_across_three_branches_is_stale_by_two(tmp_path, capsys):
    """The drift scales with the number of branches that land the same edit."""
    repo, baseline = repo_with_markers(tmp_path, 3)

    for index, name in enumerate(("branch-a", "branch-b", "branch-c")):
        assert lower_on_branch(repo, baseline, name, index, 2) == count_ratchet.EXIT_OK

    for branch in ("branch-a", "branch-b", "branch-c"):
        merge_into_main(repo, branch)
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo))

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE STALE. 0 violations < baseline 2 (-2)" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_branch_that_lowers_the_baseline_below_its_own_count_still_fails(tmp_path):
    """Control: the branch legs above pass on merit, not by accident.

    A branch that removes two markers but records only one of them is stale on
    its own, before any merge. If this passed, the tests above would prove
    nothing about the merge.
    """
    repo, baseline = repo_with_markers(tmp_path, 3)
    checkout(repo, "-b", "greedy")
    (repo / "violation_0.txt").unlink()
    (repo / "violation_1.txt").unlink()
    baseline.write_text("2\n", encoding="utf-8")
    commit_all(repo, "greedy: lower to 2 after removing two")

    rc = run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_REGRESSION
