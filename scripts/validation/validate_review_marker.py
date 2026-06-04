#!/usr/bin/env python3
"""Validate that a SHA-bound ``Reviewed-By: /review@...`` marker covers a commit.

The ``/review`` skill writes a git trailer on a PASS verdict so ``/ship`` can
prove the code being shipped was reviewed at its current state. The trailer is
the only durable, vendor-safe (no ``.agents/`` dependency) carrier: it lives in
the commit, travels in every clone, and binds to a specific SHA. See Issue #1938.

MARKER CONTRACT (the single source of truth for both the writer and this reader):

    Reviewed-By: /review@<axis1,axis2,...> on <40-or-64-hex-sha>

- ``/review@`` is a literal prefix.
- ``<axis-list>`` is one or more comma-separated axis stems (``analyst``,
  ``security``, ...). It MUST be non-empty.
- `` on `` (space-on-space) separates the axis list from the reviewed SHA.
- ``<sha>`` is the git object name of the commit whose review state the marker
  asserts: the reviewed tip.

WHY THE MARKER IS AN EMPTY COMMIT NAMING ITS PARENT (not its own SHA):
A commit cannot name its own SHA in a trailer, because the SHA is a hash of the
commit content, which includes the trailer; writing the SHA changes the SHA, and
there is no fixed point. So ``/review`` reviews the tip X, then writes an EMPTY
marker commit M on top whose trailer names X (``M``'s parent). M adds no code.
SHA-binding holds: HEAD is M only while the reviewed code (X) is HEAD's parent.
Land any new code commit and HEAD moves to a commit with no binding marker, so a
stale review cannot ship.

This validator does not amend or write. It reads the ``Reviewed-By`` trailers on
a commit (at the git I/O boundary, or passed in for tests) and answers one
question: is the commit a marker whose trailer binds its parent (the reviewed
code state)?

EXIT CODES (``AGENTS.md``, ADR-035):
    0 - A valid marker binds to the expected SHA.
    1 - No marker, malformed marker, or marker binds to a different SHA.
    2 - Configuration error (git unavailable, bad repo root, bad args).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# The trailer key the /review skill writes and /ship reads. Defined once here
# and quoted verbatim in .claude/skills/review/SKILL.md and
# .claude/commands/ship.md so the writer and reader never drift (see
# .claude/rules/canonical-source-mirror.md).
MARKER_TRAILER_KEY = "Reviewed-By"

# Parse one marker value: "/review@<axes> on <sha>". The axis list is one or
# more comma-separated stems; it must be non-empty. The SHA is 40 (sha1) or 64
# (sha256) lowercase hex characters, matching git object-name widths.
_MARKER_VALUE_RE = re.compile(
    r"^/review@(?P<axes>[A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*) on (?P<sha>[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$"
)


@dataclass(frozen=True, slots=True)
class ReviewMarker:
    """A parsed, well-formed review marker."""

    axes: tuple[str, ...]
    sha: str


def parse_marker(value: str) -> ReviewMarker | None:
    """Parse one marker trailer value into a ``ReviewMarker``.

    Returns ``None`` when ``value`` does not match the marker contract
    (empty, wrong prefix, missing SHA, empty axis list, malformed SHA).
    A malformed marker is an expected miss, not an exception: the caller
    decides how to treat it.
    """
    match = _MARKER_VALUE_RE.match(value.strip())
    if match is None:
        return None
    axes = tuple(match.group("axes").split(","))
    return ReviewMarker(axes=axes, sha=match.group("sha").lower())


def select_marker_for_sha(values: list[str], expected_sha: str) -> ReviewMarker | None:
    """Return the first valid marker among ``values`` that binds ``expected_sha``.

    ``values`` is the list of raw ``Reviewed-By`` trailer values found on a
    commit (a commit may carry more than one trailer of the same key). A marker
    binds the SHA only when it parses cleanly AND its recorded SHA equals
    ``expected_sha``. Returns ``None`` when no value satisfies both.
    """
    for value in values:
        marker = parse_marker(value)
        if marker is not None and marker.sha == expected_sha:
            return marker
    return None


def _run_git(args: list[str], repo_root: Path) -> tuple[int, str, str]:
    """Run a git command in ``repo_root``; return (exit_code, stdout, stderr).

    Bounded timeout: git is a local process but a wedged index or a network
    remote on an auto-fetching config could hang it. A 15s ceiling keeps the
    gate from stalling a ship.
    """
    if not shutil.which("git"):
        return -1, "", "git not found on PATH"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out after 15s"
    return result.returncode, result.stdout, result.stderr


def _is_option_like_ref(ref: str) -> bool:
    """Return true when ``ref`` would be parsed by git as an option."""
    return ref.startswith("-")


def resolve_sha_with_error(ref: str, repo_root: Path) -> tuple[str | None, str | None]:
    """Resolve ``ref`` and preserve git's stderr when resolution fails."""
    if _is_option_like_ref(ref):
        return None, f"invalid ref '{ref}': refs must not start with '-'"
    exit_code, stdout, stderr = _run_git(["rev-parse", "--verify", "--quiet", ref], repo_root)
    if exit_code != 0:
        return None, stderr.strip() or None
    sha = stdout.strip()
    return (sha or None), None


def resolve_sha(ref: str, repo_root: Path) -> str | None:
    """Resolve ``ref`` (e.g. ``HEAD`` or ``HEAD^``) to a full object name, or ``None``."""
    sha, _ = resolve_sha_with_error(ref, repo_root)
    return sha


def read_marker_values(ref: str, repo_root: Path) -> list[str] | None:
    """Read all ``Reviewed-By`` trailer values from the commit at ``ref``.

    Returns the list of trailer values (one per ``Reviewed-By:`` line in the
    commit's last paragraph), an empty list when the commit carries none, or
    ``None`` when git could not read the commit (bad ref, git failure).
    """
    if _is_option_like_ref(ref):
        return None
    exit_code, stdout, _ = _run_git(
        [
            "log",
            "-1",
            f"--format=%(trailers:key={MARKER_TRAILER_KEY},valueonly,unfold)",
            ref,
        ],
        repo_root,
    )
    if exit_code != 0:
        return None
    return [line for line in stdout.splitlines() if line.strip()]


def read_parent_shas(commit_sha: str, repo_root: Path) -> list[str] | None:
    """Read the direct parent SHAs for ``commit_sha``."""
    exit_code, stdout, _ = _run_git(["show", "-s", "--format=%P", commit_sha], repo_root)
    if exit_code != 0:
        return None
    return stdout.split()


def resolve_tree_sha(commit_sha: str, repo_root: Path) -> str | None:
    """Resolve ``commit_sha`` to the tree SHA it points at."""
    exit_code, stdout, _ = _run_git(["show", "-s", "--format=%T", commit_sha], repo_root)
    if exit_code != 0:
        return None
    tree_sha = stdout.strip()
    return tree_sha or None


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """The result of checking a ref for a SHA-bound marker."""

    ok: bool
    exit_code: int
    message: str


def validate_ref_argument(ref: str) -> ValidationOutcome | None:
    """Return an error outcome when ``ref`` is not safe to pass to git."""
    if shutil.which("git") is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message="git not found on PATH",
        )

    if _is_option_like_ref(ref):
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=f"invalid ref '{ref}': refs must not start with '-'",
        )

    return None


def validate_parent_shas(
    ref: str,
    head_sha: str,
    parent_shas: list[str] | None,
) -> ValidationOutcome | None:
    """Return an error outcome when parent data is missing or invalid."""
    if parent_shas is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=f"git could not read parent commits for '{ref}'",
        )

    if not parent_shas:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"{ref} ({head_sha[:12]}) has no parent commit, so it cannot be a "
                f"review marker (a marker is an empty commit on top of the reviewed "
                f"tip). Run /review on this branch."
            ),
        )

    return None


def validate_marker_commit_shape(
    ref: str,
    head_sha: str,
    parent_shas: list[str],
    repo_root: Path,
) -> ValidationOutcome | None:
    """Return an error outcome when ``ref`` is not an empty single-parent marker."""
    if len(parent_shas) != 1:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"{ref} ({head_sha[:12]}) has {len(parent_shas)} parents; a review "
                f"marker must be a single-parent empty commit. Re-run /review on a "
                f"linear branch tip."
            ),
        )

    parent_sha = parent_shas[0]
    head_tree_sha = resolve_tree_sha(head_sha, repo_root)
    parent_tree_sha = resolve_tree_sha(parent_sha, repo_root)
    if head_tree_sha is None or parent_tree_sha is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=f"git could not compare commit trees for '{ref}'",
        )

    if head_tree_sha != parent_tree_sha:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"{ref} ({head_sha[:12]}) changes files; a review marker must be an "
                f"empty commit whose Reviewed-By trailer names its parent. Re-run "
                f"/review after the code tip is ready."
            ),
        )

    return None


def validate_ref(ref: str, repo_root: Path) -> ValidationOutcome:
    """Check that ``ref`` is a marker commit binding its parent (the reviewed code).

    Resolves ``ref`` and its parent (``<ref>^``), reads the ``Reviewed-By``
    trailers on ``ref``, and confirms one is a valid marker whose recorded SHA
    equals the parent SHA. The marker is an empty commit naming the reviewed
    tip, so binding to the parent is the SHA-binding check at the heart of the
    ship gate (a commit cannot name its own SHA; see module docstring).
    """
    ref_error = validate_ref_argument(ref)
    if ref_error is not None:
        return ref_error

    head_sha, resolve_error = resolve_sha_with_error(ref, repo_root)
    if head_sha is None:
        reason = f": {resolve_error}" if resolve_error else ""
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=f"could not resolve ref '{ref}' to a commit{reason}",
        )

    parent_shas = read_parent_shas(head_sha, repo_root)
    parent_error = validate_parent_shas(ref, head_sha, parent_shas)
    if parent_error is not None:
        return parent_error
    assert parent_shas is not None

    shape_error = validate_marker_commit_shape(ref, head_sha, parent_shas, repo_root)
    if shape_error is not None:
        return shape_error

    parent_sha = parent_shas[0]
    values = read_marker_values(head_sha, repo_root)
    if values is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=f"git could not read commit '{ref}'",
        )

    if not values:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"no '{MARKER_TRAILER_KEY}: /review@...' marker on {ref} ({head_sha[:12]}). "
                f"Run /review on this branch; it writes the marker on a PASS verdict."
            ),
        )

    marker = select_marker_for_sha(values, parent_sha)
    if marker is None:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"'{MARKER_TRAILER_KEY}' marker on {ref} ({head_sha[:12]}) does not bind "
                f"the reviewed tip {parent_sha[:12]} (it reviewed a different commit, or "
                f"new code landed after review). Re-run /review."
            ),
        )

    return ValidationOutcome(
        ok=True,
        exit_code=0,
        message=(
            f"reviewed: /review@{','.join(marker.axes)} binds {parent_sha[:12]} "
            f"({len(marker.axes)} axis/axes)"
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a SHA-bound 'Reviewed-By: /review@...' marker on a commit. "
            "Used by /ship to prove the shipped code was reviewed at its current state."
        )
    )
    parser.add_argument(
        "--ref",
        default="HEAD",
        help=(
            "Commit ref to check (default: HEAD). It must be a /review marker "
            "commit whose Reviewed-By trailer binds its parent (the reviewed tip)."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help=(
            "Repository root. Defaults to the current working directory, which "
            "must be the consumer repository being shipped."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    repo_root = args.repo_root or Path.cwd()
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        print(f"[FAIL] invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    outcome = validate_ref(args.ref, repo_root)
    label = "PASS" if outcome.ok else "FAIL"
    stream = sys.stdout if outcome.ok else sys.stderr
    print(f"[{label}] {outcome.message}", file=stream)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
