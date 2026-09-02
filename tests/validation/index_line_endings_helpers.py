"""Shared fixtures for the index line-ending gate's tests (issue #5475).

Split out when the single test module crossed the 500-line `file-size`
ceiling. Everything here builds real git repositories, because the defect only
exists in a real index: `git add` would clean the CRLF away, which is the whole
reason it took a hook-free path to arrive.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- negative control: a real repository carrying the defect ---------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )


def _repo_with_crlf_blob(tmp_path: Path, name: str = "handoff.md") -> Path:
    """Build a repo holding a CRLF blob under `eol=lf`, as the API produces one.

    `git add` would clean the CRLF away, which is the whole reason the defect
    needs a hook-free path to exist. `git hash-object -w` writes the blob
    without the filter and `update-index --cacheinfo` stages it, reproducing
    what `createCommitOnBranch` uploads.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    # `*.md text` matches this repository: an explicit `text` always applies
    # the clean filter, while `text=auto` alone leaves an already-CRLF blob
    # untouched and the defect never surfaces.
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\n", newline="\n"
    )
    _git(repo, "add", ".gitattributes")

    crlf = repo / name
    crlf.write_bytes(b"line one\r\nline two\r\n")
    blob = _git(repo, "hash-object", "-w", "--no-filters", str(crlf)).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
    return repo


def _commit(repo: Path, message: str) -> None:
    _git(
        repo,
        "-c", "user.email=test@example.invalid",
        "-c", "user.name=Test",
        "commit", "--quiet", "--no-verify", "-m", message,
    )


def _porcelain(worktree: Path) -> str:
    return _git(worktree, "status", "--porcelain").stdout.strip()


# The two blobs this incident was about. Named explicitly, not just covered by
# the whole-tree guard above, so a reintroduction of these exact paths fails
# with the incident's own name attached rather than as an anonymous count.
INCIDENT_PATHS = (
    ".agents/sessions/handoffs/2026-09-01-4789-handoff.md",
    ".agents/sessions/handoffs/2026-09-01-5361-handoff.md",
)


# --- a pathname is bytes, and some byte sequences are not text -------------


def _repo_with_undecodable_crlf_blob(tmp_path: Path) -> tuple[Path, bytes]:
    """Track a CRLF blob under a filename that is not valid UTF-8.

    Git stores pathnames as bytes and imposes no encoding, so `b"bad\\xff.md"`
    is a legal tracked name on POSIX. It is the case a lossy decode destroys.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n*.md text\n", newline="\n")
    _git(repo, "add", ".gitattributes")

    raw_name = b"bad\xff.md"
    (repo / os.fsdecode(raw_name)).write_bytes(b"line one\r\nline two\r\n")
    blob = _git(
        repo, "hash-object", "-w", "--no-filters", os.fsdecode(raw_name)
    ).stdout.strip()
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"100644,{blob},{os.fsdecode(raw_name)}",
    )
    return repo, raw_name
