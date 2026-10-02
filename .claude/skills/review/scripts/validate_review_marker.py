#!/usr/bin/env python3
# taste-lint: ignore file-size, sidecar copied alone into installs, so it cannot import siblings
"""Validate that a SHA-bound ``Reviewed-By: /review@...`` marker covers a commit.

The ``/review`` skill writes a git trailer on a PASS verdict so ``/ship`` can
prove the code being shipped was reviewed at its current state. The trailer is
the only durable, vendor-safe (no ``.agents/`` dependency) carrier: it lives in
the commit, travels in every clone, and binds to a specific SHA. See Issue #1938.

MARKER CONTRACT (the single source of truth for both the writer and this reader):

    Reviewed-By: /review@<axis1,axis2,...> on <40-or-64-hex-sha>

- ``/review@`` is a literal prefix.
- ``<axis-list>`` is one or more comma-separated axis stems (``analyst``,
  ``security``, ...). It MUST be non-empty, name only discovered axes
  (``references/*.md`` stems, the local skill axes, ``correctness``), and name
  each axis once.
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
    1 - No marker, malformed marker, marker binds to a different SHA, or the
        marker names an axis outside the discovered set (or names one twice).
    2 - Configuration error (git unavailable, bad repo root, bad args, or no
        review axis directory to validate axis names against).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# The trailer key the /review skill writes and /ship reads. Defined once here
# and quoted verbatim in .claude/skills/review/SKILL.md and
# .claude/skills/ship/SKILL.md so the writer and reader never drift (see
# .claude/rules/canonical-source-mirror.md).
MARKER_TRAILER_KEY = "Reviewed-By"

# Parse one marker value: "/review@<axes> on <sha>". The axis list is one or
# more comma-separated stems; it must be non-empty. The SHA is 40 (sha1) or 64
# (sha256) lowercase hex characters, matching git object-name widths.
_MARKER_VALUE_RE = re.compile(
    r"^/review@(?P<axes>[A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*) on "
    r"(?P<sha>[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$"
)


# Axes that have no ``references/{stem}.md`` prompt but still appear in a marker.
# LOCAL_AXES copies select_axes.py:55 (canonical source, review skill scripts/
# select_axes.py) verbatim:
#   LOCAL_AXES = ("code-qualities-assessment", "doc-accuracy", "golden-principles", "taste-lints")
# These are sibling skills run with ``Skill(skill=...)``. A test locks the two
# tuples together. ``correctness`` is the always-on step 4c pass named in the
# review skill's SKILL.md ("Always-on correctness pass"); /review reports it on
# every run, so a marker may list it. This copy is stricter than select_axes.py
# in one way: it rejects any name outside these sets, where select_axes.py only
# rejects unknown names passed to --pin.
LOCAL_AXES = ("code-qualities-assessment", "doc-accuracy", "golden-principles", "taste-lints")
ALWAYS_ON_AXES = ("correctness",)


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


def find_references_dir() -> Path | None:
    """Return the ``references/`` directory beside this script's skill, or ``None``.

    The marker names axes of the skill that wrote it, so the default axis set
    comes from this script's own install, never from the repository being
    shipped. A mirror sits at ``<skill>/scripts/`` beside ``<skill>/references/``.
    The canonical copy under ``scripts/validation/`` has no such sibling; its
    caller passes ``--references-dir``.
    """
    candidate = Path(__file__).resolve().parent.parent / "references"
    return candidate if candidate.is_dir() else None


def discover_known_axes(references_dir: Path) -> frozenset[str]:
    """Return every axis name a marker may carry.

    That is each ``references/*.md`` stem, the local skill axes, and the
    always-on ``correctness`` pass.
    """
    stems = {path.stem for path in references_dir.glob("*.md")}
    return frozenset(stems | set(LOCAL_AXES) | set(ALWAYS_ON_AXES))


def default_known_axes(references_dir: Path | None = None) -> frozenset[str] | None:
    """Return the discovered axis set, or ``None`` when no axis source exists.

    ``references_dir`` wins over the directory beside this script. A directory
    with no ``*.md`` prompt is a partial install, the same condition the axis
    selector reports as exit 2, so it counts as no source: the hard-coded axes
    alone would let a forged marker pass with every canonical prompt absent.
    """
    found = references_dir if references_dir is not None else find_references_dir()
    if found is None or not found.is_dir():
        return None
    if not any(found.glob("*.md")):
        return None
    return discover_known_axes(found)


def check_axes(axes: tuple[str, ...], known_axes: frozenset[str]) -> str | None:
    """Return why ``axes`` is not a valid axis list, or ``None`` when it is.

    A duplicate name is found with one ``Counter`` pass, because set equality
    alone cannot tell ``analyst,analyst,qa`` from ``analyst,qa``. A subset is allowed:
    /review selects axes by change risk, so a marker lists the axes that ran.
    """
    unknown = sorted(set(axes) - known_axes)
    if unknown:
        return f"unknown axis name(s): {', '.join(unknown)}"
    repeated = sorted(axis for axis, count in Counter(axes).items() if count > 1)
    if repeated:
        return f"axis named more than once: {', '.join(repeated)}"
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
        result = subprocess.run(  # subprocess-encoding: strict-ok
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out after 15s"
    except UnicodeDecodeError:
        # Commit messages and paths are raw bytes on POSIX. Strict UTF-8 keeps
        # a bad decode from becoming a plausible wrong string, and this gate
        # already reports failure through the return value rather than raising.
        return -1, "", "git output was not valid UTF-8"
    return result.returncode, result.stdout, result.stderr


def _git_failure_reason(exit_code: int, stderr: str, operation: str) -> str:
    """Return a diagnostic that distinguishes git exit from internal failures."""
    reason = stderr.strip()
    if exit_code == -1:
        return reason or f"{operation} failed before git completed"
    if reason:
        return f"{operation} exited with {exit_code}: {reason}"
    return f"{operation} exited with {exit_code}"


def _with_reason(message: str, error: str | None) -> str:
    """Append git's own diagnostic to an outcome message when there is one.

    Every reader in this module returns ``(value, error)``. Flattening the
    error into a generic "git could not read X" sends the developer to run the
    same command by hand, where a lenient terminal decodes what the gate could
    not, and the real cause stays hidden.
    """
    return f"{message}: {error}" if error else message


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


def read_marker_values(ref: str, repo_root: Path) -> tuple[list[str] | None, str | None]:
    """Read all ``Reviewed-By`` trailer values from the commit at ``ref``.

    This is the one call in the gate whose stdout is commit trailer text
    rather than hex SHAs, so it is the one most likely to fail on a decode.
    The reason travels with the result.

    Returns:
        ``(values, None)`` on success, where ``values`` is one entry per
        ``Reviewed-By:`` line and may be empty. ``(None, reason)`` when git
        could not read the commit; ``reason`` is git's own message when it
        produced one.
    """
    if _is_option_like_ref(ref):
        return None, f"invalid ref '{ref}': refs must not start with '-'"
    exit_code, stdout, stderr = _run_git(
        [
            "log",
            "-1",
            f"--format=%(trailers:key={MARKER_TRAILER_KEY},valueonly,unfold)",
            ref,
        ],
        repo_root,
    )
    if exit_code != 0:
        return None, _git_failure_reason(exit_code, stderr, "git log")
    return [line for line in stdout.splitlines() if line.strip()], None


def read_parent_shas(commit_sha: str, repo_root: Path) -> tuple[list[str] | None, str | None]:
    """Read the direct parent SHAs for ``commit_sha``, preserving git's error."""
    exit_code, stdout, stderr = _run_git(["show", "-s", "--format=%P", commit_sha], repo_root)
    if exit_code != 0:
        return None, _git_failure_reason(exit_code, stderr, "git show parents")
    return stdout.split(), None


def resolve_tree_sha(commit_sha: str, repo_root: Path) -> tuple[str | None, str | None]:
    """Resolve ``commit_sha`` to its tree SHA, preserving git's error."""
    exit_code, stdout, stderr = _run_git(["show", "-s", "--format=%T", commit_sha], repo_root)
    if exit_code != 0:
        return None, _git_failure_reason(exit_code, stderr, "git show tree")
    tree_sha = stdout.strip()
    return (tree_sha or None), None


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
    read_error: str | None = None,
) -> ValidationOutcome | None:
    """Return an error outcome when parent data is missing or invalid."""
    if parent_shas is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=_with_reason(f"git could not read parent commits for '{ref}'", read_error),
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
    head_tree_sha, head_tree_error = resolve_tree_sha(head_sha, repo_root)
    parent_tree_sha, parent_tree_error = resolve_tree_sha(parent_sha, repo_root)
    if head_tree_sha is None or parent_tree_sha is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=_with_reason(
                f"git could not compare commit trees for '{ref}'",
                head_tree_error or parent_tree_error or "tree SHA was empty",
            ),
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


def bound_markers(values: list[str], parent_sha: str) -> list[ReviewMarker]:
    """Return every well-formed marker among ``values`` that binds ``parent_sha``."""
    parsed = (parse_marker(value) for value in values)
    return [marker for marker in parsed if marker is not None and marker.sha == parent_sha]


def select_valid_marker(
    markers: list[ReviewMarker],
    known_axes: frozenset[str],
) -> tuple[ReviewMarker | None, str | None]:
    """Return the first marker with a valid axis list.

    When every marker fails the axis check, the second value is the first
    marker's failure so the caller can report it.
    """
    axis_failure: str | None = None
    for marker in markers:
        failure = check_axes(marker.axes, known_axes)
        if failure is None:
            return marker, None
        axis_failure = axis_failure or failure
    return None, axis_failure


def validate_ref(
    ref: str,
    repo_root: Path,
    known_axes: frozenset[str] | None = None,
    references_dir: Path | None = None,
) -> ValidationOutcome:
    """Check that ``ref`` is a marker commit binding its parent (the reviewed code).

    Resolves ``ref`` and its parent (``<ref>^``), reads the ``Reviewed-By``
    trailers on ``ref``, and confirms one is a valid marker whose recorded SHA
    equals the parent SHA. The marker is an empty commit naming the reviewed
    tip, so binding to the parent is the SHA-binding check at the heart of the
    ship gate (a commit cannot name its own SHA; see module docstring).

    The axis list must also name only discovered axes, each once. ``known_axes``
    defaults to the set discovered beside this script; no axis directory is a
    configuration error (exit 2), not a pass.
    """
    ref_error = validate_ref_argument(ref)
    if ref_error is not None:
        return ref_error

    head_sha, resolve_error = resolve_sha_with_error(ref, repo_root)
    if head_sha is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=_with_reason(f"could not resolve ref '{ref}' to a commit", resolve_error),
        )

    parent_shas, parent_read_error = read_parent_shas(head_sha, repo_root)
    parent_error = validate_parent_shas(ref, head_sha, parent_shas, parent_read_error)
    if parent_error is not None:
        return parent_error
    assert parent_shas is not None

    shape_error = validate_marker_commit_shape(ref, head_sha, parent_shas, repo_root)
    if shape_error is not None:
        return shape_error

    parent_sha = parent_shas[0]
    values, marker_read_error = read_marker_values(head_sha, repo_root)
    if values is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=_with_reason(f"git could not read commit '{ref}'", marker_read_error),
        )

    return evaluate_marker_values(
        ref, head_sha, parent_sha, values, known_axes, references_dir
    )


def evaluate_marker_values(
    ref: str,
    head_sha: str,
    parent_sha: str,
    values: list[str],
    known_axes: frozenset[str] | None,
    references_dir: Path | None = None,
) -> ValidationOutcome:
    """Decide the outcome from the raw ``Reviewed-By`` values on a marker commit.

    The axis set is resolved here, after the shape and binding checks, so a
    missing ``references/`` directory (exit 2) never hides a stale or absent
    marker (exit 1). ``known_axes`` wins over ``references_dir``, which wins
    over the directory beside this script.
    """
    if not values:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"no '{MARKER_TRAILER_KEY}: /review@...' marker on {ref} ({head_sha[:12]}). "
                f"Run /review on this branch; it writes the marker on a PASS verdict."
            ),
        )

    markers = bound_markers(values, parent_sha)
    if not markers:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"'{MARKER_TRAILER_KEY}' marker on {ref} ({head_sha[:12]}) does not bind "
                f"the reviewed tip {parent_sha[:12]} (it reviewed a different commit, or "
                f"new code landed after review). Re-run /review."
            ),
        )

    if known_axes is None:
        known_axes = default_known_axes(references_dir)
    if known_axes is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message="review skill references/ directory missing or empty; cannot check axis names",
        )

    marker, axis_failure = select_valid_marker(markers, known_axes)
    if marker is None:
        return ValidationOutcome(
            ok=False,
            exit_code=1,
            message=(
                f"'{MARKER_TRAILER_KEY}' marker on {ref} ({head_sha[:12]}) has an invalid "
                f"axis list: {axis_failure}. Re-run /review and list only the axes that ran."
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
        "--references-dir",
        type=Path,
        default=None,
        help=(
            "Review skill references/ directory that names the valid axes. "
            "Defaults to the references/ directory beside this script's skill."
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

    outcome = validate_ref(args.ref, repo_root, references_dir=args.references_dir)
    label = "PASS" if outcome.ok else "FAIL"
    stream = sys.stdout if outcome.ok else sys.stderr
    print(f"[{label}] {outcome.message}", file=stream)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
