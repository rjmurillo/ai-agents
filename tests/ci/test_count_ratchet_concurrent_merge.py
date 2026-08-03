"""The concurrent-lowering race and the slack the ratchet accepts (issue #4057).

Two branches can each remove one violation and write the same lowered
baseline. Git merges the identical one-line edits without a conflict, so the
merged tree has improved twice while the file fell once.

The ratchet does not block that state. ``count_ratchet`` treats a count below
the baseline as an improvement and exits 0 (PR #4214), so concurrent cleanup
PRs never conflict on the shared line and the default branch does not go red
on a change none of them made. The cost is real and is pinned below: the
baseline sits above the true count until someone records it, and that gap will
absorb one later regression without firing.

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
def test_two_concurrent_baseline_lowerings_leave_slack_not_a_red_main(
    tmp_path, capsys
):
    """Both branches pass, the identical edits merge clean, and main stays green.

    This is the race issue #4057 reports. Each branch removes one violation
    and writes the same lowered value, so git sees no conflict, and the merged
    tree has improved twice while the baseline fell once. The ratchet reads
    that as an improvement rather than a regression, so the default branch
    does not go red on a change neither author made.
    """
    repo, baseline = two_branches_that_each_lower_by_one(tmp_path)

    for branch in ("branch-a", "branch-b"):
        merge_into_main(repo, branch)

    assert count_ratchet.read_baseline(baseline) == 1
    assert marker_counter(repo)(repo) == 0
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo))

    assert rc == count_ratchet.EXIT_OK
    assert "OK. 0 violations <= baseline 1 (-1 slack)" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_slack_left_by_the_race_absorbs_one_later_regression(tmp_path, capsys):
    """The price of not blocking, stated as a test rather than a caveat.

    After the race the baseline reads 1 and the tree measures 0. A change that
    reintroduces one violation takes the count back to 1, which the stale
    baseline still allows, so the gate does not fire. Recording the true count
    is what closes the gap; nothing in the ratchet forces it.
    """
    repo, baseline = two_branches_that_each_lower_by_one(tmp_path)
    for branch in ("branch-a", "branch-b"):
        merge_into_main(repo, branch)

    (repo / "violation_9.txt").write_text("x\n", encoding="utf-8")
    commit_all(repo, "reintroduce one violation")
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo))

    assert marker_counter(repo)(repo) == 1
    assert rc == count_ratchet.EXIT_OK
    assert "count == baseline 1" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_current_base_does_not_turn_the_second_branch_red(tmp_path, capsys):
    """Bringing branch-b current with main does not manufacture a failure.

    Under a strict required-checks policy the second branch has to be current
    before it merges, which re-runs this ratchet against the tree that will
    land. That tree measures 0 against a baseline of 1. Blocking there would
    turn every concurrent cleanup pair into a stuck queue, so the ratchet
    reports the slack and passes.
    """
    repo, baseline = two_branches_that_each_lower_by_one(tmp_path)
    merge_into_main(repo, "branch-a")

    bring_up_to_date(repo, "branch-b")
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_OK
    assert "OK. 0 violations <= baseline 1 (-1 slack)" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_updated_second_branch_goes_green_once_it_records_the_true_count(
    tmp_path, capsys
):
    """Recording the true count is the way to close the slack, and it works."""
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
def test_cumulative_lowering_across_three_branches_leaves_slack_of_two(
    tmp_path, capsys
):
    """The drift scales with the number of branches that land the same edit."""
    repo, baseline = repo_with_markers(tmp_path, 3)

    for index, name in enumerate(("branch-a", "branch-b", "branch-c")):
        assert lower_on_branch(repo, baseline, name, index, 2) == count_ratchet.EXIT_OK

    for branch in ("branch-a", "branch-b", "branch-c"):
        merge_into_main(repo, branch)
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo))

    assert rc == count_ratchet.EXIT_OK
    assert "OK. 0 violations <= baseline 2 (-2 slack)" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_branch_that_raises_the_count_above_the_baseline_still_fails(tmp_path, capsys):
    """Negative control: the gate above passes on merit, not because it is off.

    Every assertion in this module now expects exit 0, so a ratchet that had
    been disabled outright would satisfy all of them. A branch that adds a
    violation it does not record must still be rejected, or those tests prove
    nothing.
    """
    repo, baseline = repo_with_markers(tmp_path, 2)
    checkout(repo, "-b", "sloppy")
    (repo / "violation_9.txt").write_text("x\n", encoding="utf-8")
    commit_all(repo, "sloppy: add a violation without recording it")
    capsys.readouterr()

    rc = run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "REGRESSION. 3 violations > baseline 2" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_branch_that_lowers_the_baseline_below_its_own_count_is_slack(tmp_path):
    """Under-recording an improvement is slack, which the ratchet permits.

    A branch that removes two markers but records only one of them measures 1
    against a baseline of 2. That is the same shape the race produces, so it
    gets the same verdict.
    """
    repo, baseline = repo_with_markers(tmp_path, 3)
    checkout(repo, "-b", "greedy")
    (repo / "violation_0.txt").unlink()
    (repo / "violation_1.txt").unlink()
    baseline.write_text("2\n", encoding="utf-8")
    commit_all(repo, "greedy: lower to 2 after removing two")

    rc = run_ratchet(repo, baseline, marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_OK
