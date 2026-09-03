"""Shared fixtures for the index line-ending gate's tests (issue #5475), and
the roster of which module covers what.

Everything here builds real git repositories, because the defect only exists in
a real index: `git add` would clean the CRLF away, which is the whole reason it
took a hook-free path to arrive.

The suite is split across six modules, all of them at the 500-line `file-size`
ceiling rather than by design. Every module imports this one, so the roster
lives here and each module's own docstring says only what that module covers.
Four review rounds were spent on docstrings that named the previous split, so
the list is in one place on purpose:

- `test_check_index_line_endings.py`: the parser and the reporting contract,
  against strings the test wrote rather than a repository.
- `test_check_index_line_endings_repo.py`: real repositories. The negative
  controls, the operator-visible phantom modification, the two incident paths,
  and the HEAD and index scopes with their precedence.
- `test_check_index_line_endings_env.py`: what the gate reads that is not a
  blob. Ambient `GIT_*` isolation, the git capability floor, each scope's
  attribute source, and the three states an unresolvable HEAD can mean.
- `test_check_index_line_endings_fix.py`: what `--fix` does, and every guard
  that runs before it writes.
- `test_check_index_line_endings_paths.py`: the bytes of a tracked path. What
  the report may print for one and what a shell may be handed.
- `index_line_endings_helpers.py`: this module.

Two more live outside `tests/validation/`:
`tests/ci/test_index_line_endings_ci_wiring.py` covers the workflow wiring, and
`tests/validation/test_pre_pr_index_line_endings_wiring.py` the gate's
registration in the pre-PR sequence.
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
    crlf.parent.mkdir(parents=True, exist_ok=True)
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
