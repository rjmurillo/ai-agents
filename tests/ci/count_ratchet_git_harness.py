"""Real-git scaffolding shared by the count-ratchet test modules.

Git is the boundary under test in both modules, so it is not mocked; the
linter is not, so it is. Splitting the modules duplicated this scaffolding
once, which is how the two copies would drift.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.ci import count_ratchet


def init_repo(repo: Path) -> None:
    """A repository with an identity and a deterministic default branch."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)


def git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo`` and hand back the result without raising."""
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def commit_all(repo: Path, message: str) -> None:
    """Stage everything in ``repo`` and commit it."""
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)


def checkout(repo: Path, *argv: str) -> None:
    """Check out in ``repo``, failing the test if git refuses."""
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", *argv], check=True)


def git_checked(repo: Path, *args: str) -> None:
    """Run git in ``repo``, failing the test if it refuses."""
    subprocess.run(["git", "-C", str(repo), *args], check=True)


def git_stdout(repo: Path, *args: str) -> str:
    """Stripped stdout of a git command, failing the test if git refuses."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


def main_lowered_to_99(tmp_path: Path) -> tuple[Path, Path, str]:
    """A repository whose default branch lowered ``baseline.txt`` 100 -> 99.

    Returns ``(repo, baseline_file, main_ref)``. The commit before the lowering
    is the fork point every branch built on this is cut from, which is the shape
    issue #4057 recorded and issue #5065 re-read.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    baseline_file = repo / "baseline.txt"
    baseline_file.write_text("100\n", encoding="utf-8")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    commit_all(repo, "main: baseline=100")

    git_checked(repo, "checkout", "-q", "-b", "branch-a")
    baseline_file.write_text("99\n", encoding="utf-8")
    commit_all(repo, "branch-a: lower baseline to 99")

    git_checked(repo, "checkout", "-q", "main")
    git_checked(repo, "merge", "-q", "--ff-only", "branch-a")
    return repo, baseline_file, "main"


def run_with_count(
    repo: Path,
    baseline_file: Path,
    base_ref: str,
    count: int,
    *,
    merge_tree_backed: bool = True,
) -> int:
    """Drive ``count_ratchet.run`` over ``repo`` with the linter stubbed out.

    Git is the boundary under test in the fork-point modules, so it is real;
    the linter is not, so ``count`` stands in for it.
    """
    args = argparse.Namespace(
        baseline=baseline_file,
        repo_root=repo,
        update=False,
        base_ref=base_ref,
    )
    return count_ratchet.run(
        args,
        label="test",
        counter=lambda _: count,
        scan_error="scan failed",
        regression_advice="fix violations",
        merge_tree_backed=merge_tree_backed,
    )


class FakeCounter:
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


def run_ratchet(
    repo: Path,
    baseline: Path,
    counter,
    *,
    base_ref: str | None = None,
    merge_tree_backed: bool = True,
) -> int:
    """Drive the real entry point over ``repo`` with a fake counter.

    ``merge_tree_backed`` defaults to True because the stand-in models the five
    registered ratchets. Pass False to model the subprocess-encoding ratchet,
    whose baseline is absent from
    ``scripts/ci/merge_tree_ratchet_registry.py::RATCHETS``.
    """
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
        merge_tree_backed=merge_tree_backed,
    )
