#!/usr/bin/env python3
"""Check that a promotion candidate sits where ADR-113 decision 5 says it must.

Quoted from ``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``
decision 5: the entry point "rejects a SHA that is not an ancestor of the
default branch head or does not match the tag", so "the candidate is therefore
a merged default-branch commit".

Two checks, both reads of the local clone:

- :func:`candidate_on_branch`: the candidate commit is an ancestor of a named
  ref (the default branch head).
- :func:`tag_names_candidate`: an existing tag resolves to exactly the candidate
  commit, so a manifest for one commit cannot be attached to another release.

Each returns ``(ok, detail)`` and raises ``CandidateCheckError`` when git cannot
answer. An unanswered question is not a pass.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

GIT_TIMEOUT_SECONDS = 30
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


class CandidateCheckError(Exception):
    """Git could not answer the question, so the check proves nothing."""


class InvalidCandidateNameError(ValueError):
    """A ref or tag name is not a plain name. That is bad input, not a git failure."""


def _git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # subprocess-encoding: strict-ok
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CandidateCheckError(f"git {args[0]} could not run: {type(exc).__name__}") from exc


def _component_problem(component: str) -> bool:
    """True for a path component git refuses in a ref name."""
    return (
        not component
        or component.startswith(".")
        or component.endswith((".", ".lock"))
        or "@{" in component
    )


def _valid_name(value: str, pattern: re.Pattern[str], label: str) -> None:
    """Refuse a name git would reject, so bad input exits 2 and not 3.

    The character set excludes space, ``~ ^ : ? * [ \\`` and control characters.
    The component rules cover an empty component (``a//b``, a trailing slash),
    a leading dot, and the ``.lock`` suffix, from ``git check-ref-format``.
    """
    if not pattern.fullmatch(value) or ".." in value:
        raise InvalidCandidateNameError(f"{label} {value!r} is not a plain ref name")
    if any(_component_problem(part) for part in value.split("/")):
        raise InvalidCandidateNameError(f"{label} {value!r} is not a valid git ref name")


def candidate_on_branch(repo_root: Path, sha: str, ref: str) -> tuple[bool, str]:
    """Return whether commit ``sha`` is an ancestor of, or equal to, ``ref``."""
    _valid_name(ref, _REF_RE, "ref")
    result = _git(repo_root, ["merge-base", "--is-ancestor", sha, ref])
    if result.returncode == 0:
        return True, f"{sha[:12]} is an ancestor of {ref}"
    if result.returncode == 1:
        return False, f"{sha[:12]} is not an ancestor of {ref}"
    raise CandidateCheckError(f"git merge-base failed with exit {result.returncode}")


def tag_names_candidate(repo_root: Path, tag: str, sha: str) -> tuple[bool, str]:
    """Return whether the existing tag ``tag`` resolves to commit ``sha``."""
    _valid_name(tag, _TAG_RE, "tag")
    result = _git(repo_root, ["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
    if result.returncode == 1:
        return False, f"tag {tag} does not exist in this clone"
    if result.returncode != 0:
        raise CandidateCheckError(f"git rev-parse failed with exit {result.returncode}")
    resolved = result.stdout.strip()
    if resolved == sha:
        return True, f"tag {tag} resolves to {sha[:12]}"
    return False, f"tag {tag} resolves to {resolved[:12]}, not {sha[:12]}"


def candidate_files(repo_root: Path, sha: str) -> tuple[str, ...]:
    """Return the repository-relative paths in the candidate commit's tree.

    Read from the commit, never the working tree: the gate asks what the
    candidate contains, not what a checkout happens to hold. NUL-separated, so a
    path with a newline in it stays one path.
    """
    if not _SHA_RE.fullmatch(sha):
        raise InvalidCandidateNameError(f"candidate {sha!r} is not a 40-character commit SHA")
    result = _git(repo_root, ["ls-tree", "-r", "-z", "--name-only", sha])
    if result.returncode != 0:
        raise CandidateCheckError(f"git ls-tree failed with exit {result.returncode}")
    return tuple(name for name in result.stdout.split("\0") if name)


def changed_files(repo_root: Path, sha: str) -> tuple[str, ...]:
    """Return the paths the candidate commit changed against its first parent.

    NUL-separated. Raises ``CandidateCheckError`` when git cannot answer, which
    includes a root commit: with no parent there is no diff to compare.
    """
    if not _SHA_RE.fullmatch(sha):
        raise InvalidCandidateNameError(f"candidate {sha!r} is not a 40-character commit SHA")
    result = _git(repo_root, ["diff", "--name-only", "-z", f"{sha}^1", sha])
    if result.returncode != 0:
        raise CandidateCheckError(f"git diff failed with exit {result.returncode}")
    return tuple(name for name in result.stdout.split("\0") if name)


def parent_file(repo_root: Path, sha: str, path: str) -> str | None:
    """Return ``path`` as the candidate's first parent held it, or None if it did not.

    Raises ``CandidateCheckError`` when git cannot run or the parent is unreadable.
    """
    if not _SHA_RE.fullmatch(sha):
        raise InvalidCandidateNameError(f"candidate {sha!r} is not a 40-character commit SHA")
    if path.startswith(("/", "-")) or ".." in path.split("/"):
        raise InvalidCandidateNameError("path must be repository-relative")
    result = _git(repo_root, ["show", f"{sha}^1:{path}"])
    if result.returncode == 0:
        return result.stdout
    if result.returncode == 128 and "exists on disk, but not in" in result.stderr:
        return None
    if result.returncode == 128 and "does not exist in" in result.stderr:
        return None
    raise CandidateCheckError(f"git show failed with exit {result.returncode}")
