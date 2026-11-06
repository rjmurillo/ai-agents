#!/usr/bin/env python3
"""Export a pull request head's spec trees as data for the spec review job.

Issue #6506 workflow-ci-04: the review job holds the model key, so it checks
out the base commit and runs only base code. The pull request head arrives
here as data. This script fetches the head commit and extracts the spec and
planning trees into a directory under RUNNER_TEMP. The extraction filter skips
every symlink and hardlink, and a second pass deletes any link that remains,
so a head-controlled link cannot point the spec loader at a runner file.

Environment:
  GH_TOKEN      token for the one authenticated fetch (required)
  PR_NUMBER     pull request number (required)
  HEAD_SHA      head commit from the event payload (required)
  RUNNER_TEMP   parent of the export directory (required)

Exit codes (ADR-035): 0 success, 2 config error, 3 external (git) failure.
"""

from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

TREES = (".project-toolkit/specs", ".project-toolkit/planning")
EXPORT_DIR_NAME = "pr-head-data"
# A full SHA-1 or SHA-256 object name. Anything else, including a leading dash,
# never reaches git as an argument.
SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _git(args: list[str], *, token: str = "") -> subprocess.CompletedProcess[bytes]:
    """Run git. A token goes on the command line, never into .git/config."""
    command = ["git"]
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        command += ["-c", f"http.extraheader=AUTHORIZATION: basic {basic}"]
    return subprocess.run([*command, *args], capture_output=True, check=False)


def _has_commit(sha: str) -> bool:
    return _git(["cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0


def _has_tree(sha: str, tree: str) -> bool:
    return _git(["cat-file", "-e", f"{sha}:{tree}"]).returncode == 0


def fetch_head(pr_number: str, head_sha: str, token: str) -> bool:
    """Fetch the pull request head, falling back to the event SHA if it moved."""
    ref = f"+refs/pull/{pr_number}/head:refs/remotes/pull/head"
    if _git(["fetch", "--no-tags", "origin", ref], token=token).returncode != 0:
        return False
    if _has_commit(head_sha):
        return True
    return _git(["fetch", "--no-tags", "origin", "--", head_sha], token=token).returncode == 0


def _regular_files_only(member: tarfile.TarInfo, path: str) -> tarfile.TarInfo | None:
    """Skip links entirely, and let the stdlib data filter vet everything else."""
    if member.issym() or member.islnk():
        return None
    return tarfile.data_filter(member, path)


def export_trees(head_sha: str, destination: Path) -> None:
    """Extract each spec tree present in the head, then drop every symlink."""
    destination.mkdir(parents=True, exist_ok=True)
    for tree in TREES:
        if not _has_tree(head_sha, tree):
            continue
        archive = _git(["archive", head_sha, tree])
        if archive.returncode != 0:
            raise RuntimeError(f"git archive failed for {tree}")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(destination, filter=_regular_files_only)
    # Defense in depth behind the extraction filter.
    for path in destination.rglob("*"):
        if path.is_symlink():
            path.unlink()


def main() -> int:
    token = os.environ.get("GH_TOKEN", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    head_sha = os.environ.get("HEAD_SHA", "")
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    valid = (
        token
        and pr_number.isascii()
        and pr_number.isdecimal()
        and SHA_PATTERN.fullmatch(head_sha)
        and runner_temp
    )
    if not valid:
        print(
            "::error::GH_TOKEN, a numeric PR_NUMBER, a full-length HEAD_SHA and RUNNER_TEMP "
            "are required",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    if not fetch_head(pr_number, head_sha, token):
        print(f"::error::could not fetch the head of pull request {pr_number}", file=sys.stderr)
        return EXIT_EXTERNAL
    try:
        export_trees(head_sha, Path(runner_temp) / EXPORT_DIR_NAME)
    except (RuntimeError, tarfile.TarError, OSError) as exc:
        print(f"::error::could not export the head spec trees: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
