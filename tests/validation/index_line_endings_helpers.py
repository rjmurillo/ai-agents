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

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- negative control: a real repository carrying the defect ---------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git against `repo`, immune to the ambient `GIT_*` set.

    Tests that redirect `GIT_DIR` or `GIT_INDEX_FILE` to prove the gate ignores
    them would otherwise redirect their own fixtures and assertions too. Same
    rule the gate applies in
    `scripts/validation/index_line_endings_git.py::git_environment`.
    """
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
    )


def _staged_against_head(repo: Path) -> list[str]:
    """Paths whose staged blob differs from HEAD's: what `--fix` actually wrote.

    `check_repository` reports a path bad in both scopes once, under HEAD, so
    `[v.scope for v in violations] == ["HEAD"]` reads identically before a
    renormalize and after one. It cannot witness a write, which is what a test
    of the write-target guard has to do. This can: the fixtures stage the CRLF
    blob and commit it, so the index and HEAD agree until `--fix` runs.
    """
    output = _git(repo, "diff", "--cached", "--name-only").stdout
    return [line for line in output.split("\n") if line]


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
    """Commit without an identity or a signer the host happens to configure.

    `commit.gpgsign=false` is passed explicitly because `_git` strips `GIT_*`,
    and the suite's own defence against a host signer is the `GIT_CONFIG_COUNT`
    injection in `tests/conftest.py`, which that strip removes. On a machine
    with global signing enabled these fixture commits would otherwise reach the
    host signer and fail for a reason that has nothing to do with the test.
    `tests/conftest.py` writes the same setting the same way for its own
    fixtures: `git(main, "config", "commit.gpgsign", "false")`.
    """
    _git(
        repo,
        "-c", "user.email=test@example.invalid",
        "-c", "user.name=Test",
        "-c", "commit.gpgsign=false",
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


#: The undecodable-filename fixtures below are POSIX-only, and callers apply
#: this to say so. A pathname is bytes on POSIX and UTF-16 on NT, so
#: `os.fsdecode(b"bad\\xff.md")` has no NT spelling and the fixture raises
#: before the gate under test ever runs. Skipping is honest here: the defect
#: those tests cover cannot exist on a platform whose paths are Unicode.
posix_only_paths = pytest.mark.skipif(
    os.name == "nt", reason="pathnames are bytes on POSIX and Unicode on NT"
)


def _repo_with_undecodable_crlf_blob(tmp_path: Path) -> tuple[Path, bytes]:
    """Track a CRLF blob under a filename that is not valid UTF-8.

    Git stores pathnames as bytes and imposes no encoding, so `b"bad\\xff.md"`
    is a legal tracked name on POSIX. It is the case a lossy decode destroys.
    POSIX-only; see `posix_only_paths`.
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
