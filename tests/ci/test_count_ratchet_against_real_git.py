"""Bootstrap probes and ``--base-ref`` verdicts, run against real git.

The monkeypatched tests in ``test_taste_count_ratchet.py`` assert the branch
logic but would pass just as happily if the ref syntax were wrong, because the
stand-in matches on the subcommand alone. These exercise git itself, so a
malformed revision expression fails here instead of in CI.

The ``run`` tests below drive the real entry point against a real repository
with a fake counter. The concurrent-merge race and its enforcement point live
in ``test_count_ratchet_concurrent_merge.py``. The fork-point direction cases,
which build real branch topologies rather than dirtying one commit's working
tree, live in ``test_count_ratchet_fork_point.py``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import taste_count_ratchet as ratchet
from tests.ci.count_ratchet_git_harness import (
    FakeCounter as _FakeCounter,
)
from tests.ci.count_ratchet_git_harness import (
    commit_all as _commit_all,
)
from tests.ci.count_ratchet_git_harness import (
    init_repo as _init_repo,
)
from tests.ci.count_ratchet_git_harness import (
    run_ratchet as _run_ratchet,
)


def _repo_with_committed_baseline(tmp_path: Path, value: int) -> tuple[Path, Path]:
    """A repository whose HEAD records ``value`` in ``base.txt``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    baseline = repo / "base.txt"
    baseline.write_text(f"{value}\n", encoding="utf-8")
    _commit_all(repo, f"baseline {value}")
    return repo, baseline


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_baseline_absence_is_discriminated_against_real_git(tmp_path):
    """Pin the probes against git itself, not against a stand-in.

    The monkeypatched tests above assert the branch logic but would pass just
    as happily if the ref syntax were wrong, because the fake matches on the
    subcommand alone. This exercises `rev-parse --verify` and `cat-file -e`
    for real, so a malformed revision expression fails here instead of in CI.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True
    )
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True)

    baseline = tmp_path / "baseline.txt"
    baseline.write_text("615\n", encoding="utf-8")

    # Committed nowhere yet: this is the bootstrap shape.
    assert count_ratchet.baseline_absent_at_ref(tmp_path, "HEAD", baseline) is True

    subprocess.run(["git", "-C", str(tmp_path), "add", "baseline.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "add"], check=True)

    # Present at HEAD: not bootstrap, and readable through the same ref syntax.
    assert count_ratchet.baseline_absent_at_ref(tmp_path, "HEAD", baseline) is False
    assert count_ratchet.baseline_at_ref(tmp_path, "HEAD", baseline) == 615

    # An unresolvable ref is never bootstrap.
    assert (
        count_ratchet.baseline_absent_at_ref(tmp_path, "nosuchref", baseline) is False
    )

@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.parametrize(
    ("baseline_name", "counter"),
    [
        ("taste_count_baseline.txt", ratchet.current_count),
    ],
)
def test_the_shipped_baseline_describes_the_tracked_tree(baseline_name, counter):
    """The baseline must describe this repository, not a stale snapshot.

    It may sit slightly above the tree. Issue #4057 recorded why: two branches
    can each remove a violation and each write the same lowered baseline, git
    merges the identical edits cleanly, and the tree improves twice while the
    scalar falls once. PR #4214 accepted that slack so the default branch does
    not go red on a change none of the merging branches made.

    Demanding equality here would override that decision, and did. This test
    asserted ``actual == baseline`` from 2026-07-30 (PR #3824) until the
    concurrent-merge policy landed on 2026-08-03 (PR #4214) without removing
    it, so every collision reddened main for every contributor. Two such
    outages were root-caused on 2026-08-03 alone, at baselines 595 and 593.

    What is still enforced: the tree may never exceed the baseline, and the
    baseline may not drift more than ``MAX_BASELINE_SLACK`` above it. Run
    ``python scripts/ci/taste_count_ratchet.py`` for per-file detail.
    """
    repo_root = Path(__file__).resolve().parents[2]
    baseline_path = repo_root / "scripts" / "ci" / baseline_name
    baseline = count_ratchet.read_baseline(baseline_path)
    assert baseline is not None, f"{baseline_name} is missing or not an integer"
    problem = count_ratchet.baseline_health(counter(repo_root), baseline)
    assert problem is None, f"{baseline_name}: {problem}"

@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_baseline_outside_the_repo_is_not_bootstrap_against_real_git(tmp_path):
    """Pin the fail-open against git itself, not against the stand-in.

    `_baseline_rel` hands the probe an absolute path when the baseline does not
    live under the repo root. Git refuses that path expression, and the refusal
    must not be mistaken for an absent file.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "seed"], check=True)

    outside = tmp_path / "outside"
    outside.mkdir()
    escaping = outside / "baseline.txt"
    escaping.write_text("615\n", encoding="utf-8")

    # Absent from the tree: the genuine bootstrap shape.
    assert count_ratchet.baseline_absent_at_ref(repo, "HEAD", repo / "baseline.txt")

    # Refused by git: an error, and the old probe could not tell the two apart.
    assert count_ratchet.baseline_absent_at_ref(repo, "HEAD", escaping) is False
    refused = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"HEAD:{escaping.as_posix()}"],
        capture_output=True,
        check=False,
    )
    missing = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", "HEAD:baseline.txt"],
        capture_output=True,
        check=False,
    )
    assert refused.returncode == missing.returncode != 0


# ---------------------------------------------------------------------------
# run(): the --base-ref verdict must be named from a count it actually took
# (issue #4066)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_stale_branch_is_told_to_sync_before_it_is_told_to_fix(tmp_path, capsys):
    """The reported bug: a branch behind a base ref that lowered its baseline.

    Nothing here added a violation. The measured count is one the base ref
    already allows, so the sync remedy leads and the widening remedy is offered
    as the alternative it is, not as the diagnosis.
    """
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")
    counter = _FakeCounter(331)

    rc = _run_ratchet(repo, baseline, counter, base_ref="HEAD")

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BASELINE ABOVE BASE" in err
    assert "nothing in this tree added a violation" in err
    assert err.index("merge or rebase") < err.index("fix the violations")
    assert counter.calls == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_real_widened_allowance_still_blocks(tmp_path, capsys):
    """The gate stays closed: a genuinely widened allowance still blocks."""
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(334), base_ref="HEAD")

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BASELINE ABOVE BASE. This tree records 334, HEAD records 331 (+3)" in err
    assert "fix the violations instead of widening the allowance" in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_behind_branch_that_kept_its_own_count_is_not_blamed(tmp_path, capsys):
    """The base ref deleted violations, so the behind branch counts above it.

    ``count > base`` here and the branch still edited nothing: it holds the
    tree the base ref held before the cleanup. The old text read this as a
    widened allowance and told the author to fix violations they never added.
    """
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(334), base_ref="HEAD")

    err = capsys.readouterr().err
    assert rc == count_ratchet.EXIT_REGRESSION
    assert "If this branch did not edit the baseline, it is behind HEAD" in err
    assert "BASELINE RAISED" not in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_behind_branch_that_added_a_violation_is_not_told_it_raised(
    tmp_path, capsys
):
    """One added violation must not turn "behind" into an accusation.

    The branch measures 335 against its own baseline of 334, so it did add
    something, but it never made the 331 -> 334 baseline delta the old text
    charged it with.
    """
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(335), base_ref="HEAD")

    err = capsys.readouterr().err
    assert rc == count_ratchet.EXIT_REGRESSION
    assert "The measured count is 335." in err
    assert "If this branch did not edit the baseline" in err
    assert "331 -> 334" not in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_widening_that_added_nothing_is_told_how_to_undo_it(tmp_path, capsys):
    """A deliberate widening with no new violations needs a workable remedy.

    ``count <= base`` holds, so the old text sent this author to merge the base
    ref. Merging cannot lower a baseline this branch raised itself, so the
    advice looped. The restore remedy has to be in the message.
    """
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(331), base_ref="HEAD")

    err = capsys.readouterr().err
    assert rc == count_ratchet.EXIT_REGRESSION
    assert "If it did raise the baseline, restore 331" in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_raised_baseline_with_an_unrunnable_counter_exits_external(tmp_path, capsys):
    """A scan that could not run outranks the ratchet verdict.

    Counting first means an unrunnable linter is reported as the external
    error it is, instead of being masked by a baseline comparison that would
    have blocked anyway for a reason nobody could verify.
    """
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(None), base_ref="HEAD")

    assert rc == count_ratchet.EXIT_EXTERNAL
    assert "scan failed" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_an_unreadable_base_ref_still_exits_external(tmp_path, capsys):
    """A ref that does not resolve is an error, never a waived comparison."""
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    counter = _FakeCounter(331)

    rc = _run_ratchet(repo, baseline, counter, base_ref="refs/heads/does-not-exist")

    assert rc == count_ratchet.EXIT_EXTERNAL
    assert "could not read the baseline" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_bootstrap_still_passes_when_the_base_ref_has_no_baseline(tmp_path, capsys):
    """Reordering the count must not break the first run of a new ratchet."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _commit_all(repo, "seed")
    baseline = repo / "base.txt"
    baseline.write_text("331\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(331), base_ref="HEAD")

    assert rc == count_ratchet.EXIT_OK
    assert "bootstrap" in capsys.readouterr().out
