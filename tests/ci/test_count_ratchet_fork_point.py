"""Fork-point direction and the ``--base-ref`` verdict, run against real git.

Split out of ``test_count_ratchet_against_real_git.py`` when that module passed
the 500-line taste ceiling. What lives here is one question: given a base ref
whose baseline sits below this tree's, which way did THIS checkout move the
number, and what does the ratchet do about each answer. Four answers, all
measured from ``git merge-base`` rather than guessed from two endpoint reads:
raised, lowered, unchanged with a merge-tree backstop, and unchanged without
one. The three ways the comparison fails to happen at all moved to
``test_count_ratchet_fork_failures.py`` when adding the last two of them pushed
this module to 496 lines against the 500-line taste ceiling.

Git is the boundary under test, so it is not mocked; the linter is, so it is.
Issues #4066 (do not name a cause you did not measure) and #5065 (do not block
a branch for a number main moved underneath it).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from tests.ci.count_ratchet_git_harness import commit_all as _commit_all
from tests.ci.count_ratchet_git_harness import git_checked as _git
from tests.ci.count_ratchet_git_harness import git_stdout as _git_stdout
from tests.ci.count_ratchet_git_harness import init_repo as _init_repo
from tests.ci.count_ratchet_git_harness import main_lowered_to_99 as _main_lowered_to_99
from tests.ci.count_ratchet_git_harness import run_with_count as _run_against


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_branch_that_never_moved_the_number_is_not_blocked(tmp_path, capsys) -> None:
    """Issue #5065: being behind the base ref is not a violation.

    Branch B is cut from the pre-lowering commit and edits nothing. Its
    recorded 100 matches the fork point's 100, so the branch did not raise an
    allowance; ``main`` lowered one underneath it. Blocking here made a
    bookkeeping scalar a merge gate: on 2026-08-03, with
    ``scripts/ci/taste_count_baseline.txt`` at 598 on ``main``, 31 of 33 open
    non-draft PRs recorded a higher number and failed on it.

    The count leg still runs: 100 <= 100 here, so the verdict is OK.
    """
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)
    _git(repo, "checkout", "-q", "-b", "branch-b", f"{main_ref}~1")

    rc = _run_against(repo, baseline_file, main_ref, count=100)

    assert rc == count_ratchet.EXIT_OK
    out = capsys.readouterr().out
    assert "BEHIND BASE (not blocking)" in out
    assert "never moved the number" in out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_behind_base_does_not_short_circuit_the_count_leg(tmp_path, capsys) -> None:
    """The two legs are independent, and the non-blocking one must not excuse.

    ``_base_ref_verdict`` returns None for a behind-base branch, which is the
    same value it returns when it has nothing to say, so ``run`` falls through
    to ``count > baseline`` exactly as before. This branch is behind (fork
    point 100 == recorded 100, base 99) and also measures 101 on its own
    merits, so the BEHIND BASE notice prints and the count leg still blocks.

    Without this case the diff proves only that the notice is reachable, never
    that the gate survives it. A ``return EXIT_OK`` in place of that ``return
    None`` would satisfy every other test in this section.
    """
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)
    _git(repo, "checkout", "-q", "-b", "branch-e", f"{main_ref}~1")

    rc = _run_against(repo, baseline_file, main_ref, count=101)

    assert rc == count_ratchet.EXIT_REGRESSION
    captured = capsys.readouterr()
    assert "BEHIND BASE (not blocking)" in captured.out
    assert "BASELINE ABOVE BASE" not in captured.err
    assert "REGRESSION. 101 violations > baseline 100" in captured.err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_branch_that_raised_the_number_itself_still_blocks(tmp_path, capsys) -> None:
    """The mirror of the case above: the widening hole stays shut.

    Same fork point, but this branch commits 101. The fork point records 100,
    so the branch is what moved the scalar, and that is the only route by which
    a higher number reaches ``main``.
    """
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)
    _git(repo, "checkout", "-q", "-b", "branch-c", f"{main_ref}~1")
    baseline_file.write_text("101\n", encoding="utf-8")
    _commit_all(repo, "branch-c: widen the allowance")

    rc = _run_against(repo, baseline_file, main_ref, count=99)

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE ABOVE BASE" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_an_uncommitted_raise_blocks_like_a_committed_one(tmp_path, capsys) -> None:
    """Edge: the pre-push hook scans the working tree, so a dirty edit counts.

    ``read_baseline`` reads the file on disk. A raise that is staged, or not
    even staged, must reach the same verdict as one that is committed, or the
    local gate is trivially side-stepped.
    """
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)
    _git(repo, "checkout", "-q", "-b", "branch-d", f"{main_ref}~1")
    baseline_file.write_text("101\n", encoding="utf-8")

    rc = _run_against(repo, baseline_file, main_ref, count=99)

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE ABOVE BASE" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_branch_that_lowered_the_number_is_not_told_it_raised(tmp_path, capsys) -> None:
    """The cleanup-PR shape: this branch lowered, the base lowered further.

    ``baseline_move`` used to be ``recorded != at_fork``, so any difference in
    either direction landed on ``_above_base_message``. A branch that removed
    violations and ran ``--update`` was then told to "restore" the base value,
    a number it never recorded, and to stop "widening the allowance" it had
    just narrowed. Both halves are the inverse of what it did.

    Fork records 100, this branch commits 95 measuring 95, and main is at 90.
    The recorded value is still above the base, so it blocks: the one-line
    baseline file conflicts on merge anyway, and passing it would install a
    ceiling main has already fallen below.
    """
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)
    _git(repo, "checkout", "-q", "main")
    baseline_file.write_text("90\n", encoding="utf-8")
    _commit_all(repo, "main: lower baseline to 90")

    _git(repo, "checkout", "-q", "-b", "branch-cleanup", f"{main_ref}~2")
    baseline_file.write_text("95\n", encoding="utf-8")
    _commit_all(repo, "branch-cleanup: lower baseline to 95")

    rc = _run_against(repo, baseline_file, main_ref, count=95)

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BASELINE LOWERED BEHIND BASE" in err
    assert "The fork point records 100, this tree records 95" in err
    assert "records 90" in err
    assert "restore 90" not in err
    assert "widening the allowance" not in err
    assert "BASELINE ABOVE BASE" not in err


def _main_moved_then_lowered_to_99(tmp_path: Path) -> tuple[Path, Path, str, str]:
    """Main gains an unrelated commit, then lowers ``baseline.txt`` 100 -> 99.

    Returns ``(repo, baseline_file, main_ref, base_at_trigger)``. The extra
    commit is what makes a merge-ref stand-in possible: a PR branch cut from the
    commit before it is not a descendant of ``base_at_trigger``, so merging that
    base produces a real merge commit instead of "Already up to date".
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    baseline_file = repo / "baseline.txt"
    baseline_file.write_text("100\n", encoding="utf-8")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _commit_all(repo, "main: baseline=100")

    (repo / "unrelated.txt").write_text("moved\n", encoding="utf-8")
    _commit_all(repo, "main: an unrelated change")

    baseline_file.write_text("99\n", encoding="utf-8")
    _commit_all(repo, "main: lower baseline to 99")
    return repo, baseline_file, "main", "main~1"


def _merge_ref_head(repo: Path, *, cut_from: str, branch: str, base_at_trigger: str) -> None:
    """Leave ``repo`` on a detached merge commit shaped like refs/pull/N/merge.

    ``actions/checkout`` with no ``ref:`` checks out that ref on a
    ``pull_request`` event, so HEAD in both ratchet jobs is a merge of the PR
    head into the base as of trigger time, on a detached HEAD, not a branch tip.
    Every other test in this module builds HEAD as a plain branch tip, and the
    fork-point read is the one thing here whose answer depends on HEAD's
    ancestry shape.
    """
    _git(repo, "checkout", "-q", "-b", branch, cut_from)
    (repo / f"{branch}.txt").write_text("work\n", encoding="utf-8")
    _commit_all(repo, f"{branch}: branch-side work")
    _git(repo, "checkout", "-q", "--detach", branch)
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", base_at_trigger)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_merge_ref_head_that_never_moved_the_number_is_not_blocked(
    tmp_path, capsys
) -> None:
    """Issue #5065 on the topology CI actually evaluates.

    The merged tree carries the fork point's 100 because neither side touched
    the baseline, ``main`` has since lowered it to 99, and the fork point of a
    merge commit resolves to its second parent, the base as of trigger time.
    """
    repo, baseline_file, main_ref, base_at_trigger = _main_moved_then_lowered_to_99(
        tmp_path
    )
    _merge_ref_head(
        repo, cut_from=f"{main_ref}~2", branch="branch-f", base_at_trigger=base_at_trigger
    )

    assert _git_stdout(repo, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert len(_git_stdout(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    assert baseline_file.read_text(encoding="utf-8").strip() == "100"

    rc = _run_against(repo, baseline_file, main_ref, count=100)

    assert rc == count_ratchet.EXIT_OK
    assert "BEHIND BASE (not blocking)" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_merge_ref_head_that_raised_the_number_still_blocks(tmp_path, capsys) -> None:
    """The mirror on the same topology: the widening hole stays shut on a merge ref.

    The branch side commits 101, so the merged tree records 101 against a fork
    point of 100. Without this case the merge-ref pair would prove only that
    the notice is reachable there, never that the gate survives it.
    """
    repo, baseline_file, main_ref, base_at_trigger = _main_moved_then_lowered_to_99(
        tmp_path
    )
    _git(repo, "checkout", "-q", "-b", "branch-g", f"{main_ref}~2")
    baseline_file.write_text("101\n", encoding="utf-8")
    _commit_all(repo, "branch-g: widen the allowance")
    _git(repo, "checkout", "-q", "--detach", "branch-g")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", base_at_trigger)

    assert _git_stdout(repo, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert baseline_file.read_text(encoding="utf-8").strip() == "101"

    rc = _run_against(repo, baseline_file, main_ref, count=99)

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE ABOVE BASE" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_count_above_the_baseline_still_regresses(tmp_path) -> None:
    """Control: the count leg is untouched by the fork-point read."""
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)

    assert _run_against(repo, baseline_file, main_ref, count=100) == (
        count_ratchet.EXIT_REGRESSION
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_current_branch_at_its_baseline_passes(tmp_path) -> None:
    """Control: the ordinary green path still returns OK."""
    repo, baseline_file, main_ref = _main_lowered_to_99(tmp_path)

    assert _run_against(repo, baseline_file, main_ref, count=99) == count_ratchet.EXIT_OK
