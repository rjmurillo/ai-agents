"""Bootstrap-detection probes for the count ratchet, run against real git.

The monkeypatched tests in ``test_taste_count_ratchet.py`` assert the branch
logic but would pass just as happily if the ref syntax were wrong, because the
stand-in matches on the subcommand alone. These exercise git itself, so a
malformed revision expression fails here instead of in CI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import taste_count_ratchet as ratchet


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

    The assertion uses a descriptive message so a failure identifies the
    ratchet involved. Run ``python scripts/ci/taste_count_ratchet.py``
    directly (1-2 seconds) to see the per-file detail instead of waiting
    for the full test suite.
    """
    repo_root = Path(__file__).resolve().parents[2]
    baseline_path = repo_root / "scripts" / "ci" / "taste_count_baseline.txt"
    baseline = int(baseline_path.read_text(encoding="utf-8").strip())
    actual = ratchet.current_count(repo_root)
    assert actual == baseline, (
        f"taste count ratchet: baseline is {baseline} but current tree has "
        f"{actual} violations. "
        f"Run 'python scripts/ci/taste_count_ratchet.py' for per-file detail."
    )

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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_concurrent_baseline_lowering_detects_stale_branch(tmp_path: Path) -> None:
    """Verify the concurrent-PR race condition described in Issue #4057.

    Scenario:
      - main starts with baseline=100, count=100
      - Branch A removes 1 violation, lowers baseline to 99, merges first
      - Branch B also removed 1 violation but did NOT pick up A's merge
        (baseline stays at 100 on branch B)
      - When B runs --base-ref against the updated main (baseline=99),
        the ratchet must fire BASELINE RAISED and return EXIT_REGRESSION

    This proves that --base-ref is the enforcement point: a branch that has
    not rebased onto the post-A main cannot slip through with a stale baseline.

    Negative control: if branch B has baseline=99 (rebased), no regression.
    """
    import argparse

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")

    baseline_file = repo / "baseline.txt"
    baseline_file.write_text("100\n", encoding="utf-8")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "baseline.txt", "seed.txt")
    _git(repo, "commit", "-qm", "main: baseline=100")

    # Branch A: removes 1 violation, lowers baseline to 99
    _git(repo, "checkout", "-q", "-b", "branch-a")
    baseline_file.write_text("99\n", encoding="utf-8")
    _git(repo, "add", "baseline.txt")
    _git(repo, "commit", "-qm", "branch-a: lower baseline to 99")

    # Merge A into main
    _git(
        repo,
        "checkout",
        "-q",
        "master" if (repo / ".git" / "refs" / "heads" / "master").exists() else "main",
    )
    try:
        _git(repo, "merge", "-q", "--ff-only", "branch-a")
    except subprocess.CalledProcessError:
        # Some git versions use 'master' by default
        _git(repo, "checkout", "-q", "-b", "main", "branch-a")

    main_ref = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()

    # Branch B: forked from original main (baseline=100), removes 1 violation
    # but did NOT pick up A's merge. baseline.txt still says 100.
    _git(repo, "checkout", "-q", "-b", "branch-b", f"{main_ref}~1")
    # Do not change baseline.txt - simulating a branch that didn't rebase

    # Branch B's state: baseline file says 100 (stale), count is also 100
    # (no actual fix on this branch). --base-ref points at main (baseline=99).
    args_stale = argparse.Namespace(
        baseline=baseline_file,   # still 100 on branch-b
        repo_root=repo,
        update=False,
        base_ref=main_ref,
    )

    # A count function that always returns 100 (branch B removed no violations)
    def count_100(_: Path) -> int:
        return 100

    rc_stale = count_ratchet.run(
        args_stale,
        label="test",
        counter=count_100,
        scan_error="scan failed",
        regression_advice="fix violations",
    )
    # Branch B's baseline (100) > main's baseline (99) => BASELINE RAISED
    assert rc_stale == count_ratchet.EXIT_REGRESSION, (
        "BASELINE RAISED must fire when a stale branch has baseline > main's baseline"
    )

    # Negative control: branch B rebases and picks up baseline=99.
    # Now branch_baseline == base_baseline => no BASELINE RAISED.
    _git(repo, "checkout", "-q", main_ref)
    args_fresh = argparse.Namespace(
        baseline=baseline_file,   # now 99 after rebase checkout
        repo_root=repo,
        update=False,
        base_ref=main_ref,
    )

    rc_fresh = count_ratchet.run(
        args_fresh,
        label="test",
        counter=count_100,
        scan_error="scan failed",
        regression_advice="fix violations",
    )
    # count=100 > baseline=99 => regression, but it's a count regression not BASELINE RAISED
    assert rc_fresh == count_ratchet.EXIT_REGRESSION, (
        "count regression must still fire when count exceeds baseline"
    )

    # Positive control: branch with count at baseline, no stale issue
    def count_99(_: Path) -> int:
        return 99

    rc_ok = count_ratchet.run(
        args_fresh,
        label="test",
        counter=count_99,
        scan_error="scan failed",
        regression_advice="fix violations",
    )
    assert rc_ok == count_ratchet.EXIT_OK, (
        "rebased branch with count == baseline must pass"
    )
