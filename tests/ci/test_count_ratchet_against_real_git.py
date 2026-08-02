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
