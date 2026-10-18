#!/usr/bin/env python3
# taste-lint: ignore file-size, sidecar copied alone into installs, so it cannot import siblings
"""Validate that a SHA-bound ``Reviewed-By: /review@...`` marker covers a commit.

The ``/review`` skill writes a git trailer on a PASS verdict so ``/ship`` can
prove the code being shipped was reviewed at its current state. The trailer is
the only durable, vendor-safe (no ``.agents/`` dependency) carrier: it lives in
the commit, travels in every clone, and binds to a specific SHA. See Issue #1938.

MARKER CONTRACT (the single source of truth for both the writer and this reader):

    Reviewed-By: /review@<axis1,axis2,...> on <40-or-64-hex-sha>
    Review-Artifact: sha256:<64-hex-digest-of-the-review-report>

The commit body also carries the review report that the digest covers:

    --- review report ---
    Reviewed-SHA: <the same sha the Reviewed-By trailer names>
    <axis>: <VERDICT>          (one row per axis in the Reviewed-By list)
    --- end review report ---

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

WHY THE MARKER CARRIES A REVIEW REPORT (Issue #6438): a bare trailer is a
sentence anyone can type, so a subagent that never ran the axes could write
``git commit --allow-empty --trailer "Reviewed-By: ..."`` and pass every gate.
The report is the reviewer's artifact: the reviewed SHA plus one verdict row per
axis. The ``Review-Artifact`` digest binds the trailer to that exact text. A
digest cannot prove who wrote the report; it makes the bare-trailer forgery
fail and makes a fabricated report a deliberate act that review can see. Proof
of identity needs a signing key or a CI-run review, which this gate does not
attempt.

WHY A CLEAN MERGE OF THE BASE REF MAY SIT ABOVE THE MARKER (Issue #6509): the
author finishes ``/review``, then main moves, and syncing the branch adds a merge
commit above M. That merge brings in code main already reviewed and changes none
of the reviewed code, so demanding a new review for it only costs a full axis
re-run. The tip is accepted when it is a clean merge of the base ref (default
``origin/main``): two parents, the second reachable from the base ref, and a tree
equal to what ``git merge-tree --write-tree`` computes for the two parents. The
first parent is then judged as the marker, and merges can stack. A merge with
conflict edits, an extra edit, or a second parent that is not on the base ref is
new, unreviewed code and still fails. Known limit: the second parent may be any
ancestor of the base ref, so merging an older main commit brings back code main has
since reverted; main's own review covered that code when it landed.
``git merge-tree --write-tree`` stores the merged tree objects in the object
database; it moves no ref and touches no file.

This validator does not amend or write. It reads the ``Reviewed-By`` trailers on
a commit (at the git I/O boundary, or passed in for tests) and answers one
question: is the commit a marker whose trailer binds its parent (the reviewed
code state) and whose report backs the trailer? ``--digest FILE`` prints the
digest of a report file so the writer never hand-computes it.

EXIT CODES (``AGENTS.md``, ADR-035):
    0 - A valid marker binds to the expected SHA.
    1 - No marker, malformed marker, marker binds to a different SHA, the
        marker names an axis outside the discovered set (or names one twice),
        or the review report is missing, altered, or does not back the axes.
    2 - Configuration error (git unavailable, bad repo root, bad args, or no
        review axis directory to validate axis names against).

``--digest REPORT_FILE`` mode has its own codes:
    0 - The digest was printed.
    1 - The file does not hold exactly one report block.
    2 - The file cannot be read.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

# The trailer key the /review skill writes and /ship reads. Defined once here
# and quoted verbatim in .claude/skills/review/resources/marker-and-no-task.md
# (the writer contract) and .claude/skills/ship/SKILL.md so the writer and
# reader never drift (see
# .claude/rules/canonical-source-mirror.md).
MARKER_TRAILER_KEY = "Reviewed-By"

# The digest trailer and the report delimiters. Quoted verbatim in
# .claude/skills/review/resources/marker-and-no-task.md (the writer contract)
# so the writer and this reader never drift.
ARTIFACT_TRAILER_KEY = "Review-Artifact"
REPORT_BEGIN = "--- review report ---"
REPORT_END = "--- end review report ---"

# Parse one marker value: "/review@<axes> on <sha>". The axis list is one or
# more comma-separated stems; it must be non-empty. The SHA is 40 (sha1) or 64
# (sha256) lowercase hex characters, matching git object-name widths.
_MARKER_VALUE_RE = re.compile(
    r"^/review@(?P<axes>[A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*) on "
    r"(?P<sha>[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$"
)

_ARTIFACT_VALUE_RE = re.compile(r"^sha256:(?P<digest>[0-9a-f]{64})$")
_REPORT_SHA_RE = re.compile(r"^Reviewed-SHA: (?P<sha>[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$")
_REPORT_ROW_RE = re.compile(r"^(?P<axis>[A-Za-z0-9_-]+): (?P<verdict>[A-Z_]+)$")

# A report row passes the marker when its verdict is one /review writes a marker
# for: PASS, or a WARN the reviewer acknowledged (review SKILL.md "Write the
# SHA-bound PASS marker"). COMPLIANT and PARTIAL are the spec-compliance
# spellings that merge into PASS and WARN.
PASSING_VERDICTS = frozenset({"PASS", "COMPLIANT", "WARN", "PARTIAL"})

# The security axis is stricter: a WARN or PARTIAL there is an open security
# finding, not an acknowledged style note, so it never backs a marker that lets
# a CRITICAL-path push through (issue #6506). Mirrored by
# detect_infrastructure.py SECURITY_PASSING_VERDICTS; test_security_review_artifact.py
# asserts the two sets match.
SECURITY_AXIS = "security"
SECURITY_PASSING_VERDICTS = frozenset({"PASS", "COMPLIANT"})

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

# The ref a clean merge must pull from, and the longest chain of syncs the walk
# below a tip will follow before it gives up and asks for a fresh review.
DEFAULT_BASE_REF = "origin/main"
MAX_MAIN_MERGE_HOPS = 25


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


def read_marker_values(
    ref: str, repo_root: Path, key: str = MARKER_TRAILER_KEY
) -> tuple[list[str] | None, str | None]:
    """Read all ``key`` trailer values (default ``Reviewed-By``) from the commit at ``ref``.

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
            f"--format=%(trailers:key={key},valueonly,unfold)",
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


def read_commit_message(ref: str, repo_root: Path) -> tuple[str | None, str | None]:
    """Read the full commit message of ``ref``, preserving git's error."""
    if _is_option_like_ref(ref):
        return None, f"invalid ref '{ref}': refs must not start with '-'"
    exit_code, stdout, stderr = _run_git(["log", "-1", "--format=%B", ref], repo_root)
    if exit_code != 0:
        return None, _git_failure_reason(exit_code, stderr, "git log message")
    return stdout, None


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
    axes: tuple[str, ...] = ()


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


@dataclass(frozen=True, slots=True)
class MarkerTarget:
    """The commit to judge as the marker, found below any clean merges of the base ref."""

    commit: str
    parents: list[str]
    merges: int = 0


def _merge_failure(ref: str, commit_sha: str, why: str, exit_code: int = 1) -> ValidationOutcome:
    """Return the outcome for a two-parent tip that is not a clean merge of the base ref."""
    return ValidationOutcome(
        ok=False,
        exit_code=exit_code,
        message=(
            f"{ref} ({commit_sha[:12]}) has 2 parents; a review marker must be a "
            f"single-parent empty commit, and only a clean merge of the base ref may sit "
            f"above one: {why}. Re-run /review on a linear branch tip."
        ),
    )


def _second_parent_on_base(
    second: str, base_ref: str, repo_root: Path
) -> tuple[bool, str | None, bool]:
    """Return ``(on_base, reason, git_failed)`` for ``second`` against ``base_ref``.

    ``merge-base --is-ancestor`` exits 0 for yes and 1 for no. Exit 128 means the
    base ref does not exist, which fails the merge check without a config error:
    a consumer that never fetched it simply has no proof the merge came from main.
    Any other code (timeout, git missing) is a git failure.
    """
    if _is_option_like_ref(base_ref):
        return False, f"invalid base ref '{base_ref}': refs must not start with '-'", False
    exit_code, _, stderr = _run_git(["merge-base", "--is-ancestor", second, base_ref], repo_root)
    if exit_code == 0:
        return True, None, False
    if exit_code == 1:
        return False, f"its second parent {second[:12]} is not on {base_ref}", False
    if exit_code == 128:
        return False, f"base ref {base_ref} could not be resolved: {stderr.strip()}", False
    return False, _git_failure_reason(exit_code, stderr, "git merge-base"), True


def _clean_merge_tree(
    first: str, second: str, repo_root: Path
) -> tuple[str | None, str | None, bool]:
    """Return ``(tree, reason, git_failed)`` for a trial merge of ``first`` and ``second``.

    ``git merge-tree --write-tree`` exits 1 when the merge has conflicts, which
    a clean sync never has.
    """
    exit_code, stdout, stderr = _run_git(
        ["merge-tree", "--write-tree", "--no-messages", first, second], repo_root
    )
    if exit_code == 0 and stdout.strip():
        return stdout.splitlines()[0].strip(), None, False
    if exit_code == 1:
        return None, "the merge needed conflict resolution", False
    return None, _git_failure_reason(exit_code, stderr, "git merge-tree"), True


def step_over_main_merge(
    ref: str,
    commit_sha: str,
    parent_shas: list[str],
    base_ref: str,
    repo_root: Path,
) -> tuple[str | None, ValidationOutcome | None]:
    """Return ``(first_parent, None)`` when ``commit_sha`` is a clean merge of ``base_ref``.

    Otherwise return ``(None, outcome)``. The outcome is exit 1 when the commit is
    not provably a clean merge, and exit 2 when git itself failed.
    """
    first, second = parent_shas
    on_base, why, git_failed = _second_parent_on_base(second, base_ref, repo_root)
    if not on_base:
        return None, _merge_failure(ref, commit_sha, why or "unknown", 2 if git_failed else 1)
    merged_tree, why, git_failed = _clean_merge_tree(first, second, repo_root)
    if merged_tree is None:
        return None, _merge_failure(ref, commit_sha, why or "unknown", 2 if git_failed else 1)
    tip_tree, tree_error = resolve_tree_sha(commit_sha, repo_root)
    if tip_tree is None:
        return None, _merge_failure(ref, commit_sha, tree_error or "tree unreadable", 2)
    if tip_tree != merged_tree:
        return None, _merge_failure(
            ref, commit_sha, "the merge changes files beyond a clean merge of the base ref"
        )
    return first, None


def find_marker_target(
    ref: str,
    head_sha: str,
    parent_shas: list[str],
    base_ref: str,
    repo_root: Path,
) -> MarkerTarget | ValidationOutcome:
    """Walk below clean merges of ``base_ref`` to the commit that must be the marker.

    A single-parent tip is its own target. Each two-parent tip must pass
    ``step_over_main_merge``; its first parent is the next commit to judge. A
    commit with any other parent count is returned as is, and the shape check
    that follows reports it.
    """
    commit, parents, merges = head_sha, parent_shas, 0
    while len(parents) == 2:
        if merges >= MAX_MAIN_MERGE_HOPS:
            return _merge_failure(
                ref,
                commit,
                f"the branch stacks more than {MAX_MAIN_MERGE_HOPS} merges of the base ref",
            )
        first, failure = step_over_main_merge(ref, commit, parents, base_ref, repo_root)
        if failure is not None:
            return failure
        assert first is not None
        read_parents, read_error = read_parent_shas(first, repo_root)
        parent_error = validate_parent_shas(ref, first, read_parents, read_error)
        if parent_error is not None:
            return parent_error
        assert read_parents is not None
        commit, parents, merges = first, read_parents, merges + 1
    return MarkerTarget(commit=commit, parents=parents, merges=merges)


def with_merge_note(outcome: ValidationOutcome, merges: int, base_ref: str) -> ValidationOutcome:
    """Add the count of skipped merges to a passing outcome's message."""
    if merges == 0:
        return outcome
    noun = "merge" if merges == 1 else "merges"
    note = f" (above {merges} clean {noun} of {base_ref})"
    return replace(outcome, message=outcome.message + note)


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
    base_ref: str = DEFAULT_BASE_REF,
) -> ValidationOutcome:
    """Check that ``ref`` is a marker commit binding its parent (the reviewed code).

    Resolves ``ref`` and its parent (``<ref>^``), reads the ``Reviewed-By``
    trailers on ``ref``, and confirms one is a valid marker whose recorded SHA
    equals the parent SHA. The marker is an empty commit naming the reviewed
    tip, so binding to the parent is the SHA-binding check at the heart of the
    ship gate (a commit cannot name its own SHA; see module docstring).

    When ``ref`` is a clean merge of ``base_ref`` (Issue #6509), the walk first
    steps below it, and the marker is judged on the first parent.

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

    target = find_marker_target(ref, head_sha, parent_shas, base_ref, repo_root)
    if isinstance(target, ValidationOutcome):
        return target

    shape_error = validate_marker_commit_shape(ref, target.commit, target.parents, repo_root)
    if shape_error is not None:
        return shape_error

    values, marker_read_error = read_marker_values(target.commit, repo_root)
    if values is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=_with_reason(f"git could not read commit '{ref}'", marker_read_error),
        )

    parent_sha = target.parents[0]
    outcome = evaluate_marker_values(
        ref, target.commit, parent_sha, values, known_axes, references_dir
    )
    if not outcome.ok:
        return outcome
    outcome = (
        validate_review_artifact(target.commit, parent_sha, outcome.axes, repo_root) or outcome
    )
    return with_merge_note(outcome, target.merges, base_ref) if outcome.ok else outcome


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
        axes=marker.axes,
    )


def extract_report(text: str) -> tuple[list[str] | None, str | None]:
    """Return the report lines between the delimiters in ``text``, or why none.

    Trailing whitespace and blank lines are dropped, because ``git commit``
    cleans a message and the digest must survive that. Exactly one block is
    allowed: a second block would let a reader and a writer hash different text.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    begins = [i for i, line in enumerate(lines) if line == REPORT_BEGIN]
    ends = [i for i, line in enumerate(lines) if line == REPORT_END]
    if len(begins) != 1 or len(ends) != 1 or begins[0] > ends[0]:
        return None, (
            f"needs exactly one '{REPORT_BEGIN}' ... '{REPORT_END}' block in the commit body"
        )
    return [line for line in lines[begins[0] + 1 : ends[0]] if line], None


def report_digest(report: list[str]) -> str:
    """Return the SHA-256 hex digest of the report lines, one per line, LF-ended."""
    payload = "".join(f"{line}\n" for line in report).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def check_report_digest(report: list[str], digest_values: list[str]) -> str | None:
    """Return why no ``Review-Artifact`` trailer matches ``report``, or ``None``."""
    digests = [
        m.group("digest") for v in digest_values if (m := _ARTIFACT_VALUE_RE.match(v.strip()))
    ]
    if not digests:
        return f"no well-formed '{ARTIFACT_TRAILER_KEY}: sha256:<64 hex>' trailer"
    if report_digest(report) not in digests:
        return f"'{ARTIFACT_TRAILER_KEY}' digest does not match the review report text"
    return None


def passing_verdicts_for(axis: str) -> frozenset[str]:
    """Return the verdicts that let ``axis`` back a marker."""
    return SECURITY_PASSING_VERDICTS if axis == SECURITY_AXIS else PASSING_VERDICTS


def check_report_rows(report: list[str], parent_sha: str, axes: tuple[str, ...]) -> str | None:
    """Return why ``report`` does not back a marker over ``axes``, or ``None``.

    The report must name the reviewed tip, carry exactly one passing row per
    marker axis, and carry no other line.
    """
    sha_lines = [_REPORT_SHA_RE.match(line) for line in report]
    named = [m.group("sha").lower() for m in sha_lines if m]
    if named != [parent_sha]:
        return f"report must name 'Reviewed-SHA: {parent_sha[:12]}' exactly once"
    rows = [line for line, m in zip(report, sha_lines, strict=True) if m is None]
    parsed = [_REPORT_ROW_RE.match(line) for line in rows]
    if not all(parsed):
        return "report has a line that is neither Reviewed-SHA nor '<axis>: <VERDICT>'"
    verdicts = {m.group("axis"): m.group("verdict") for m in parsed if m}
    if len(verdicts) != len(rows) or set(verdicts) != set(axes):
        return f"report rows must be exactly the marker axes: {', '.join(axes)}"
    failing = sorted(a for a, v in verdicts.items() if v not in passing_verdicts_for(a))
    if failing:
        return f"report has a non-passing verdict for: {', '.join(failing)}"
    return None


def check_review_artifact(
    message: str, digest_values: list[str], parent_sha: str, axes: tuple[str, ...]
) -> str | None:
    """Return why the commit message does not carry a valid review artifact, or ``None``."""
    report, failure = extract_report(message)
    if report is None:
        return failure
    return check_report_digest(report, digest_values) or check_report_rows(report, parent_sha, axes)


def validate_review_artifact(
    head_sha: str,
    parent_sha: str,
    axes: tuple[str, ...],
    repo_root: Path,
) -> ValidationOutcome | None:
    """Return an error outcome when the marker commit lacks a valid review artifact."""
    message, message_error = read_commit_message(head_sha, repo_root)
    digests, digest_error = read_marker_values(head_sha, repo_root, ARTIFACT_TRAILER_KEY)
    if message is None or digests is None:
        return ValidationOutcome(
            ok=False,
            exit_code=2,
            message=_with_reason(
                f"git could not read the review artifact on {head_sha[:12]}",
                message_error or digest_error,
            ),
        )
    failure = check_review_artifact(message, digests, parent_sha, axes)
    if failure is None:
        return None
    return ValidationOutcome(
        ok=False,
        exit_code=1,
        message=(
            f"marker {head_sha[:12]} has no valid review artifact: {failure}. "
            f"A bare '{MARKER_TRAILER_KEY}' trailer does not show a review ran. "
            f"Re-run /review; it writes the report and digest."
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
        "--base-ref",
        default=DEFAULT_BASE_REF,
        help=(
            "Ref a merge above the marker must pull from (default: origin/main). A tip "
            "that is a clean merge of this ref keeps the marker below it valid."
        ),
    )
    parser.add_argument(
        "--digest",
        type=Path,
        default=None,
        metavar="REPORT_FILE",
        help=(
            "Print the Review-Artifact digest of the review report block in "
            "REPORT_FILE and exit. The writer uses it so nobody hand-computes a hash."
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


def print_report_digest(report_file: Path) -> int:
    """Print ``sha256:<digest>`` for the report block in ``report_file``; return an exit code."""
    try:
        text = report_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"[FAIL] cannot read report file {report_file}: {exc}", file=sys.stderr)
        return 2
    report, failure = extract_report(text)
    if report is None:
        print(f"[FAIL] report file {failure}", file=sys.stderr)
        return 1
    print(f"sha256:{report_digest(report)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.digest is not None:
        return print_report_digest(args.digest)

    repo_root = args.repo_root or Path.cwd()
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        print(f"[FAIL] invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    outcome = validate_ref(
        args.ref, repo_root, references_dir=args.references_dir, base_ref=args.base_ref
    )
    label = "PASS" if outcome.ok else "FAIL"
    stream = sys.stdout if outcome.ok else sys.stderr
    print(f"[{label}] {outcome.message}", file=stream)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
