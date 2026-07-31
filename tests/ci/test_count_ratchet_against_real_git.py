"""Bootstrap-detection probes for the count ratchet, run against real git.

The monkeypatched tests in ``test_taste_count_ratchet.py`` assert the branch
logic but would pass just as happily if the ref syntax were wrong, because the
stand-in matches on the subcommand alone. These exercise git itself, so a
malformed revision expression fails here instead of in CI.

The ``run`` tests below drive the real entry point against a real repository
with a fake counter. Git is the boundary under test, so it is not mocked; the
linter is not, so it is.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import taste_count_ratchet as ratchet


def _init_repo(repo: Path) -> None:
    """A repository with an identity and a deterministic default branch."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)


class _FakeCounter:
    """Stand-in for the linter scan that records how often it ran.

    The call count is the assertion that matters for issue #4066: the verdict
    must not name a violation count it never measured.
    """

    def __init__(self, value: int | None) -> None:
        self.value = value
        self.calls = 0

    def __call__(self, _root: Path) -> int | None:
        self.calls += 1
        return self.value


def _run_ratchet(
    repo: Path,
    baseline: Path,
    counter,
    *,
    base_ref: str | None = None,
) -> int:
    argv = ["--repo-root", str(repo), "--baseline", str(baseline)]
    if base_ref is not None:
        argv += ["--base-ref", base_ref]
    args = count_ratchet.build_parser("ratchet", baseline).parse_args(argv)
    return count_ratchet.run(
        args,
        label="ratchet",
        counter=counter,
        scan_error="scan failed",
        regression_advice="fix them.",
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
def test_the_shipped_baseline_matches_the_tracked_tree():
    """The baseline must describe this repository, not a stale snapshot.

    A baseline above the real count is dead allowance: violations could be
    added up to the gap without the gate noticing. A baseline below it means
    main is already red.
    """
    repo_root = Path(__file__).resolve().parents[2]
    baseline_path = repo_root / "scripts" / "ci" / "taste_count_baseline.txt"
    baseline = int(baseline_path.read_text(encoding="utf-8").strip())
    assert ratchet.current_count(repo_root) == baseline

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
def test_a_stale_branch_is_told_to_sync_not_to_fix_violations(tmp_path, capsys):
    """The reported bug: a branch behind a base ref that lowered its baseline.

    Nothing here added a violation. The measured count is one the base ref
    already allows, so the remedy is to merge the base ref, not to hunt for
    three violations that do not exist.
    """
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")
    counter = _FakeCounter(331)

    rc = _run_ratchet(repo, baseline, counter, base_ref="HEAD")

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BRANCH BEHIND BASE" in err
    assert "Fix the violations" not in err
    assert counter.calls == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_real_widened_allowance_still_reports_baseline_raised(tmp_path, capsys):
    """The gate stays closed: a genuinely widened allowance still blocks."""
    repo, baseline = _repo_with_committed_baseline(tmp_path, 331)
    baseline.write_text("334\n", encoding="utf-8")

    rc = _run_ratchet(repo, baseline, _FakeCounter(334), base_ref="HEAD")

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE RAISED. 331 -> 334 (+3)" in capsys.readouterr().err


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


# ---------------------------------------------------------------------------
# run(): concurrent lowerings merge cleanly and leave the tree stale
# (issue #4057)
# ---------------------------------------------------------------------------


def _marker_counter(repo: Path):
    """Count the marker files still on disk. Stands in for a linter scan."""

    def _count(_root: Path) -> int:
        return len(list(repo.glob("violation_*.txt")))

    return _count


def _repo_with_markers(tmp_path: Path, count: int) -> tuple[Path, Path]:
    """A repository holding ``count`` markers and a baseline that matches."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    for index in range(count):
        (repo / f"violation_{index}.txt").write_text("x\n", encoding="utf-8")
    baseline = repo / "base.txt"
    baseline.write_text(f"{count}\n", encoding="utf-8")
    _commit_all(repo, f"seed {count}")
    return repo, baseline


def _lower_on_branch(repo: Path, baseline: Path, name: str, marker: int, to: int) -> int:
    """Cut ``name`` from main, drop one marker, record ``to``, and check it."""
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", name], check=True)
    (repo / f"violation_{marker}.txt").unlink()
    baseline.write_text(f"{to}\n", encoding="utf-8")
    _commit_all(repo, f"{name}: lower to {to}")
    return _run_ratchet(repo, baseline, _marker_counter(repo), base_ref="main")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_two_concurrent_baseline_lowerings_leave_the_merged_tree_stale(
    tmp_path, capsys
):
    """Both branches pass, the identical edits merge clean, and main goes red.

    This is the race issue #4057 reports. Each branch removes one violation
    and writes the same lowered value, so git sees no conflict, but the merged
    tree has improved twice while the baseline fell once.
    """
    repo, baseline = _repo_with_markers(tmp_path, 2)

    assert _lower_on_branch(repo, baseline, "branch-a", 0, 1) == count_ratchet.EXIT_OK
    assert _lower_on_branch(repo, baseline, "branch-b", 1, 1) == count_ratchet.EXIT_OK

    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    for branch in ("branch-a", "branch-b"):
        merge = _git(repo, "merge", "--no-ff", "-q", "-m", f"merge {branch}", branch)
        assert merge.returncode == 0, merge.stderr

    assert count_ratchet.read_baseline(baseline) == 1
    assert _marker_counter(repo)(repo) == 0
    capsys.readouterr()

    rc = _run_ratchet(repo, baseline, _marker_counter(repo))

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BASELINE STALE. 0 violations < baseline 1 (-1)" in err
    assert "merged without conflict" in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cumulative_lowering_across_three_branches_is_stale_by_two(tmp_path, capsys):
    """The drift scales with the number of branches that land the same edit."""
    repo, baseline = _repo_with_markers(tmp_path, 3)

    for index, name in enumerate(("branch-a", "branch-b", "branch-c")):
        assert _lower_on_branch(repo, baseline, name, index, 2) == count_ratchet.EXIT_OK

    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    for branch in ("branch-a", "branch-b", "branch-c"):
        merge = _git(repo, "merge", "--no-ff", "-q", "-m", f"merge {branch}", branch)
        assert merge.returncode == 0, merge.stderr
    capsys.readouterr()

    rc = _run_ratchet(repo, baseline, _marker_counter(repo))

    assert rc == count_ratchet.EXIT_REGRESSION
    assert "BASELINE STALE. 0 violations < baseline 2 (-2)" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_branch_that_lowers_the_baseline_below_its_own_count_still_fails(tmp_path):
    """Control: the branch legs above pass on merit, not by accident.

    A branch that removes two markers but records only one of them is stale on
    its own, before any merge. If this passed, the two tests above would prove
    nothing about the merge.
    """
    repo, baseline = _repo_with_markers(tmp_path, 3)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "greedy"], check=True)
    (repo / "violation_0.txt").unlink()
    (repo / "violation_1.txt").unlink()
    baseline.write_text("2\n", encoding="utf-8")
    _commit_all(repo, "greedy: lower to 2 after removing two")

    rc = _run_ratchet(repo, baseline, _marker_counter(repo), base_ref="main")

    assert rc == count_ratchet.EXIT_REGRESSION
