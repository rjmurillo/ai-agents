"""The three ways the fork-point comparison fails to happen, run against real git.

Split out of ``test_count_ratchet_fork_point.py`` when adding the last two of
these pushed that module to 496 lines against the 500-line taste ceiling, the
same move that module records having made out of
``test_count_ratchet_against_real_git.py``.

The three belong together because they were one for a while. ``baseline_move``
returned a bare None for all of them, so ``FORK POINT UNREADABLE`` and its "this
checkout's history is unrelated to <base>: fetch the real base branch" answered
for every one. Only the first is about reachability. The other two are a fork
point git named on the first try whose baseline is absent or will not parse, and
for those the fetch remedy cannot terminate the reader's loop.

All three block. What each case pins is that it blocks under its OWN message and
its own exit code, so a future edit that re-collapses them fails here rather than
shipping a confident wrong diagnosis. Issues #4066 (do not name a cause you did
not measure) and #5065.
"""

from __future__ import annotations

import shutil
import subprocess
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
def test_an_unreadable_fork_point_fails_closed(tmp_path, capsys) -> None:
    """Negative: git cannot name a fork point, so the ratchet blocks.

    An unrelated history leaves ``git merge-base`` with nothing to report.
    Reading that as "this branch changed nothing" would wave through the
    widened allowance the check exists to catch, so it blocks.

    It blocks under its OWN message. Reusing ``BASELINE ABOVE BASE`` here told a
    contributor who never touched the baseline to "restore" the base value, an
    accusation this branch of the code explicitly could not verify, which is
    what ``_above_base_message`` exists to avoid.

    Exits 3 rather than 1. Nothing measured here says this branch widened an
    allowance, which is the claim ``EXIT_REGRESSION`` makes; what happened is
    that a git read could not answer, which is external.
    """
    repo, baseline_file, _ = _main_lowered_to_99(tmp_path)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    _init_repo(unrelated)
    (unrelated / "other.txt").write_text("other\n", encoding="utf-8")
    (unrelated / "baseline.txt").write_text("98\n", encoding="utf-8")
    _commit_all(unrelated, "unrelated root")
    _git(repo, "fetch", "-q", str(unrelated), "main:unrelated")

    rc = _run_against(repo, baseline_file, "unrelated", count=99)

    assert rc == count_ratchet.EXIT_EXTERNAL
    err = capsys.readouterr().err
    assert "FORK POINT UNREADABLE" in err
    assert "histories are unrelated" in err or "unrelated to unrelated" in err
    assert "did raise the baseline" not in err
    assert "BASELINE ABOVE BASE" not in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_shallow_clone_is_told_to_unshallow(tmp_path, capsys) -> None:
    """The other unreadable-fork-point shape, and the one CI can produce.

    ``.github/workflows/pytest.yml`` fetches the base ref without ``--depth``
    precisely so no step writes ``.git/shallow``; if one ever does, every
    ratchet in that job loses its fork point at once. The remedy differs from
    the unrelated-history case, so the message has to name which one it is.

    Built with a real ``git clone --depth=1`` rather than a hand-written graft,
    because ``rev-parse --is-shallow-repository`` is what the message reads and
    only a genuine shallow clone exercises it.
    """
    origin, _, _ = _main_lowered_to_99(tmp_path)
    _git(origin, "checkout", "-q", "-b", "detached-work", "main~1")

    clone = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", "--branch", "detached-work",
         f"file://{origin}", str(clone)],
        check=True,
    )
    assert (clone / ".git" / "shallow").exists(), "clone was not shallow"
    _git(clone, "fetch", "-q", "--depth=1", f"file://{origin}", "main:refs/heads/base")

    rc = _run_against(clone, clone / "baseline.txt", "base", count=99)

    assert rc == count_ratchet.EXIT_EXTERNAL
    err = capsys.readouterr().err
    assert "FORK POINT UNREADABLE" in err
    assert "git fetch --unshallow" in err
    assert "did raise the baseline" not in err
    assert "BASELINE ABOVE BASE" not in err


def _fork_without_a_readable_baseline(
    tmp_path: Path, *, at_fork: str | None
) -> tuple[Path, Path, str]:
    """A branch at 100 over a base at 99, forked where the baseline is unusable.

    ``at_fork`` is what the fork commit records: None writes no baseline file
    at all, a string writes that text verbatim. Both leave ``git merge-base``
    able to name the fork point without trouble, which is the property that
    separates these two states from the unrelated-history and shallow-clone
    ones and makes the reachability remedies wrong for them.

    Returns ``(repo, baseline_file, fork_sha)``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    baseline_file = repo / "baseline.txt"
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    if at_fork is not None:
        baseline_file.write_text(at_fork, encoding="utf-8")
    _commit_all(repo, "main: the fork point")
    fork = _git_stdout(repo, "rev-parse", "HEAD")

    baseline_file.write_text("99\n", encoding="utf-8")
    _commit_all(repo, "main: baseline=99")

    _git(repo, "checkout", "-q", "-b", "branch-h", fork)
    baseline_file.write_text("100\n", encoding="utf-8")
    _commit_all(repo, "branch-h: baseline=100")
    return repo, baseline_file, fork


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_fork_point_with_no_baseline_is_not_reported_as_unreachable(
    tmp_path, capsys
) -> None:
    """``_fork_point`` succeeded; only the second read failed. Say so.

    Here git names the fork point on the first try and the baseline was simply
    added after the fork, so a fetch changes nothing and the reader is sent
    round a loop that cannot terminate.

    Blocks, and under ``EXIT_CONFIG``: the baseline file is the thing that is
    wrong, which is the class ``run`` already reports for a baseline missing
    from the working tree.
    """
    repo, baseline_file, fork = _fork_without_a_readable_baseline(tmp_path, at_fork=None)

    rc = _run_against(repo, baseline_file, "main", count=99)

    assert rc == count_ratchet.EXIT_CONFIG
    err = capsys.readouterr().err
    assert "FORK POINT RECORDS NO BASELINE" in err
    assert fork in err
    assert "fetching more of it changes nothing" in err
    assert "FORK POINT UNREADABLE" not in err
    assert "histories are unrelated" not in err
    assert "git fetch --unshallow" not in err
    assert "BASELINE ABOVE BASE" not in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_malformed_baseline_at_the_fork_point_is_not_reported_as_unreachable(
    tmp_path, capsys
) -> None:
    """The third failure the single None collapsed, and its own remedy.

    The fork commit tracks the file, so ``baseline_absent_at_ref`` is False and
    the state is neither of the other two: reachable history, present file,
    unreadable value. It blocks under ``EXIT_EXTERNAL`` because the failure is
    the read rather than the ratchet's own configuration, and it must not
    borrow the absent case's "merge or rebase so the fork point lands on a
    commit that records it", which would not help when the commit does record
    one.
    """
    repo, baseline_file, fork = _fork_without_a_readable_baseline(
        tmp_path, at_fork="not-a-number\n"
    )

    rc = _run_against(repo, baseline_file, "main", count=99)

    assert rc == count_ratchet.EXIT_EXTERNAL
    err = capsys.readouterr().err
    assert "FORK POINT BASELINE UNREADABLE" in err
    assert fork in err
    assert "not an integer" in err
    assert "FORK POINT RECORDS NO BASELINE" not in err
    assert "FORK POINT UNREADABLE" not in err
    assert "histories are unrelated" not in err
    assert "BASELINE ABOVE BASE" not in err
