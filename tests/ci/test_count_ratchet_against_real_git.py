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
from tests.ci.count_ratchet_git_harness import (
    commit_all as _commit_all,
)
from tests.ci.count_ratchet_git_harness import (
    init_repo as _init_repo,
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
