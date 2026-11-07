#!/usr/bin/env python3
"""Export a pull request head's spec trees as data for the spec review job.

Issue #6506 workflow-ci-04: the review job holds the model key, so it checks
out the base commit and runs only base code. The pull request head arrives
here as data. This script fetches the head commit and writes the regular files
of the spec and planning trees into a directory under RUNNER_TEMP. It reads
blobs from the git object store and writes only mode 100644 and 100755 entries,
so a head-controlled symlink never exists on disk for the spec loader to follow.
The spec loader and the ref extractor also refuse any ref that leaves
`.project-toolkit/specs` or `.project-toolkit/planning`.

Environment:
  GH_TOKEN      token for the one authenticated fetch (required)
  PR_NUMBER     pull request number (required)
  HEAD_SHA      head commit from the event payload (required)
  RUNNER_TEMP   parent of the export directory (required)

Exit codes (ADR-035): 0 success, 2 config error, 3 external (git) failure.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
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
    # main() matches HEAD_SHA against SHA_PATTERN and requires an ASCII decimal
    # PR_NUMBER. The command is an argument list, never a shell string.
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


# Git tree modes for a regular file. A symlink is 120000 and a submodule is
# 160000, so neither is ever written.
REGULAR_FILE_MODES = frozenset({"100644", "100755"})


def _safe_relative(path: str) -> bool:
    """True for a plain relative path with no empty, `.`, or `..` segment."""
    parts = path.split("/")
    return bool(path) and not path.startswith("/") and all(p not in ("", ".", "..") for p in parts)


def export_trees(head_sha: str, destination: Path) -> None:
    """Write each regular file of the head's spec trees under ``destination``.

    Files are read as blobs, not extracted from an archive, so a link or a
    crafted member name never reaches the filesystem.
    """
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    for tree in TREES:
        if not _has_tree(head_sha, tree):
            continue
        listing = _git(["ls-tree", "-r", "-z", "--full-tree", head_sha, "--", tree])
        if listing.returncode != 0:
            raise RuntimeError(f"git ls-tree failed for {tree}")
        for entry in listing.stdout.decode("utf-8", "surrogateescape").split("\0"):
            if not entry:
                continue
            meta, _, name = entry.partition("\t")
            mode, kind, blob = meta.split(" ")
            if kind != "blob" or mode not in REGULAR_FILE_MODES or not _safe_relative(name):
                continue
            target = (root / name).resolve()
            if not target.is_relative_to(root):
                continue
            content = _git(["cat-file", "blob", blob])
            if content.returncode != 0:
                raise RuntimeError(f"git cat-file failed for {name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.stdout)


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
    except OSError as exc:
        # A local filesystem problem is a config error under ADR-035.
        print(f"::error::could not write the head spec trees: {exc!r}", file=sys.stderr)
        return EXIT_CONFIG
    except (RuntimeError, ValueError) as exc:
        print(f"::error::could not export the head spec trees: {exc!r}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
