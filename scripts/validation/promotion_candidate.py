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


def _valid_name(value: str, pattern: re.Pattern[str], label: str) -> None:
    if not pattern.fullmatch(value) or ".." in value:
        raise InvalidCandidateNameError(f"{label} {value!r} is not a plain ref name")


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
