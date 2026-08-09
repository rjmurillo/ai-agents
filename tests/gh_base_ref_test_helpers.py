"""Shared git-repo builders for the GitHub PR-base ref test suites.

`tests/test_self_tracking_upstream.py` (self-tracking-upstream detection) and
`tests/test_gh_base_ref.py` (`_gh_base_ref` probe/cache/reset) both drive real
throwaway git repositories with a deterministic committer identity, so the
builders live here instead of being duplicated across the two files.

Kept out of `conftest.py` because these builders are specific to the
`checks_common` base-ref suites; a generic name in the package-wide conftest
would be visible to every validation test module.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _init_git_repo(
    path: Path,
    *,
    bare: bool = False,
    initial_branch: str = "main",
) -> None:
    """Initialise a git repo with deterministic identity for tests."""
    args = ["git", "init"]
    if bare:
        args.append("--bare")
    args.extend(["-b", initial_branch])
    subprocess.run(args, cwd=path, check=True, capture_output=True)
    if not bare:
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=path,
            check=True,
            capture_output=True,
        )


def _commit(repo: Path, file_rel: str, contents: str, message: str) -> None:
    target = repo / file_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")
    subprocess.run(
        ["git", "add", "--", file_rel],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )
