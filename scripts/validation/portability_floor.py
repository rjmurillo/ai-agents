"""The evidence a portability ratchet is floored against.

`portability_baseline` decides whether a replacement baseline may be written.
That decision is only as good as its reading of the predecessor, and the
predecessor is the one input an attacker controls: it is a file in the tree
that the same run wanting the ratchet lowered can edit first.

So the reading lives here, apart from the writing. Everything in this module
answers one question, what the previous debt provably was, and answers it from
the strongest witness available rather than the most convenient one. Absence of
debt is only ever concluded from a tool that answered, never from a tool that
failed.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

Sections = dict[str, dict[str, int]]

COUNTED_SECTIONS = ("files", "marker_files")
"""Every baseline section that records a count somebody can regress.

`files` counts violations, where lower is better. `marker_files` counts
suppressed references, where the value must stay exact. Both are debt records,
so both need the same protection; guarding only the first leaves a writable
hole in the same artifact.
"""


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    env = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
    }
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            env=env,
            check=False,
        )
    except OSError:
        return None


def _was_recorded(repo_root: Path, path: Path) -> bool | None:
    """Report whether branch history has the baseline, None when git cannot answer."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return False

    proc = _run_git(repo_root, "log", "-1", "--format=%H", "HEAD", "--", str(rel))
    if proc is None:
        return None
    if proc.returncode == 0:
        return bool(proc.stdout.strip())

    refs = _run_git(repo_root, "show-ref", "--head")
    if refs is None:
        return None
    if refs.returncode == 1 and not refs.stdout:
        return False
    return None


def _coerce_counts(section: object, name: str) -> tuple[dict[str, int] | None, str | None]:
    """Convert one baseline section to counts, reporting why it is unusable."""
    if not isinstance(section, dict):
        return None, f"section {name!r} is not a JSON object"
    counts: dict[str, int] = {}
    for key, value in section.items():
        # `int()` is too generous to be a floor. It reads `false` as 0, which
        # permits everything, and truncates `4.9` to 4, which lowers the bar by
        # one without looking like a number changed. A floor may only be built
        # from a JSON integer, so anything else is a refusal.
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"the count for {key!r} in {name!r} is not an integer"
        if value < 0:
            return None, f"the count for {key!r} in {name!r} is negative"
        counts[str(key)] = value
    return counts, None


def _unguarded_sections(data: Mapping[str, Any]) -> list[str]:
    """Name any object section this module does not know how to guard.

    The replacement payload is rebuilt from the scan, so a section absent from
    `COUNTED_SECTIONS` is not merely left uncompared, it is deleted by the very
    write that ignores it. Refusing by name turns a silent erasure into a build
    failure that says which section needs guarding.

    Every object counts, not only the ones whose values are integers today. A
    section holding an empty object, or strings, or booleans is erased by the
    same write, and a guard that only notices integers invites the attacker to
    pick another shape.
    """
    return sorted(
        name
        for name, value in data.items()
        if name not in COUNTED_SECTIONS and isinstance(value, dict)
    )


def _sections_from_text(raw: str) -> tuple[Sections | None, str | None]:
    """Parse one baseline document into its counted sections."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the baseline is not valid JSON ({exc.msg}, line {exc.lineno})"
    if not isinstance(data, dict):
        return None, "the baseline is not a JSON object"

    unguarded = _unguarded_sections(data)
    if unguarded:
        return None, (
            "the baseline records counts this guard does not know how to protect "
            f"({', '.join(unguarded)}); the replacement would delete them, so add "
            "them to COUNTED_SECTIONS before writing"
        )

    if "files" not in data:
        # The legacy flat schema is a bare path-to-count object. It is still
        # readable, so it is compared rather than refused; refusing would block
        # an honest contributor whose checkout predates the nested schema.
        counts, problem = _coerce_counts(data, "files")
        if problem:
            return None, problem
        return {"files": counts or {}}, None

    sections: Sections = {}
    for name in COUNTED_SECTIONS:
        if name not in data:
            continue
        counts, problem = _coerce_counts(data[name], name)
        if problem:
            return None, problem
        sections[name] = counts or {}
    return sections, None


def _tree_entries(
    repo_root: Path, treeish: str
) -> tuple[list[tuple[str, str, str]] | None, str | None]:
    """List one level of a committed tree as `(kind, object id, name)`."""
    listing = _run_git(repo_root, "ls-tree", "-z", treeish)
    if listing is None or listing.returncode != 0:
        return None, "git could not list the committed baseline directory"

    entries = []
    for record in listing.stdout.decode("utf-8", "replace").split("\0"):
        if not record:
            continue
        meta, _, name = record.partition("\t")
        fields = meta.split()
        if len(fields) != 3:
            return None, f"git returned a tree entry this guard cannot read ({record!r})"
        entries.append((fields[1], fields[2], name))
    return entries, None


def _descend(
    entries: list[tuple[str, str, str]], component: str
) -> tuple[tuple[str, str, str] | None, str | None]:
    """Pick the committed entry a path component names, or say why it cannot.

    Every candidate that matches case-insensitively is collected before
    anything is decided. Deciding on the first one instead refused a path git
    tracks exactly whenever a case twin happened to sort ahead of it, and the
    exact match is the one the caller asked for.
    """
    folded = [entry for entry in entries if entry[2].casefold() == component.casefold()]
    if not folded:
        return None, None
    for entry in folded:
        if entry[2] == component:
            return entry, None

    tracked = ", ".join(sorted(repr(entry[2]) for entry in folded))
    return None, (
        f"git tracks {tracked} where the baseline path says {component!r}; those "
        "differ only by case, so on a case-insensitive filesystem the write "
        "would reach a file this lookup would report as untracked"
    )


def _committed_directory(
    repo_root: Path, parts: tuple[str, ...]
) -> tuple[list[tuple[str, str, str]] | None, str | None]:
    """List the committed tree that should hold the baseline.

    Walked one component at a time rather than handed to git as a pathspec.
    A pathspec is matched case-sensitively, so a parent spelled with different
    case listed nothing, and nothing was read as "no committed copy exists" by
    the caller. On a case-insensitive filesystem the write still landed on the
    real file, which is the floor being erased by a spelling.
    """
    treeish = "HEAD"
    for component in parts:
        entries, problem = _tree_entries(repo_root, treeish)
        if problem or entries is None:
            return None, problem
        entry, problem = _descend(entries, component)
        if problem or entry is None:
            return None, problem
        kind, oid, _ = entry
        if kind != "tree":
            return None, (
                f"the committed path stops at {component!r}, which is a {kind} "
                "rather than a directory"
            )
        treeish = oid
    return _tree_entries(repo_root, treeish)


def _tracked_blob(repo_root: Path, rel: Path) -> tuple[str | None, str | None]:
    """Return the HEAD blob id for `rel`, or a reason the floor cannot be read.

    `(None, None)` means HEAD provably tracks nothing at that path, which is
    what a genuinely new baseline looks like. Every other failure returns a
    reason, because a guard that reads its floor through a command is disarmed
    by anything that makes the command fail. Treating "git errored" the same as
    "the file is new" hands the attacker a lever: break the lookup and the
    ratchet has no floor left to enforce.
    """
    parts = rel.parts
    if not parts:
        return None, "the baseline path names no file"

    entries, problem = _committed_directory(repo_root, parts[:-1])
    if problem or entries is None:
        return None, problem

    entry, problem = _descend(entries, parts[-1])
    if problem or entry is None:
        return None, problem

    kind, oid, name = entry
    if kind != "blob":
        return None, f"the committed baseline is not a regular file ({name!r} is a {kind})"
    return oid, None


def _committed_blob(repo_root: Path, path: Path) -> tuple[str | None, str | None]:
    """Name the object id HEAD records for this baseline, or say why it cannot.

    Split from the read below because locating the blob and parsing it fail for
    unrelated reasons. Keeping them together made one function where half the
    branches were about git plumbing and half were about JSON, which is the
    shape that hides a missing case in either half.

    Returns `(None, None)` only when the repository answered and the answer was
    that no committed copy exists.
    """
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        # Provably outside the repository, so git tracks no copy and there is
        # no floor to apply. `--baseline` supports this; it is not a failure.
        return None, None
    except OSError as exc:
        return None, f"the baseline path could not be resolved ({exc.strerror})"

    inside = _run_git(repo_root, "rev-parse", "--git-dir")
    if inside is None or inside.returncode != 0:
        return None, (
            "the baseline is not inside a readable git repository, so the "
            "committed copy that floors this ratchet cannot be consulted"
        )

    head = _run_git(repo_root, "rev-parse", "--verify", "--quiet", "HEAD")
    if head is None:
        return None, "git could not be run to read the committed baseline"
    if head.returncode != 0:
        if head.stdout.strip():
            return None, "git could not identify HEAD"
        return _unborn_or_refuse(repo_root)

    return _tracked_blob(repo_root, rel)


def _unborn_or_refuse(repo_root: Path) -> tuple[str | None, str | None]:
    """Decide whether an unresolvable HEAD means no commits or a broken pointer.

    A repository that has never been committed to and one whose HEAD names a
    branch somebody deleted answer `rev-parse --verify --quiet HEAD` the same
    way: non-zero, empty. Reading that single answer as "nothing is committed"
    is what let an edit to one file inside `.git` erase the floor, because the
    worktree copy then became the only surviving witness to the old debt.

    So ask a question that has an answer instead. `for-each-ref` reports the
    refs that exist without going through HEAD, and it succeeds on a fresh
    repository, returning nothing. Nothing is the only reading that permits a
    missing floor; a ref that exists means commits exist and HEAD is the part
    that is broken, which is a reason to stop, not to proceed unprotected.
    """
    refs = _run_git(repo_root, "for-each-ref", "--format=%(objectname)", "--count=1")
    if refs is None or refs.returncode != 0:
        return None, "git could not list the repository's refs to confirm it has no commits"
    if refs.stdout.strip():
        return None, (
            "HEAD does not resolve but the repository has refs, so it holds "
            "commits whose baseline should floor this write; refusing rather "
            "than trusting the working tree copy alone"
        )
    # The repository answered, and the answer was that it holds no refs at all,
    # which is the one honest way to have nothing committed to floor against.
    return None, None


def _committed_sections(repo_root: Path, path: Path) -> tuple[Sections | None, str | None]:
    """Read the baseline as HEAD records it, the one copy an edit cannot reach.

    Every other witness to the old debt lives in the working tree, where the
    same run that wants the ratchet lowered can rewrite it first. `git show`
    reads the committed object instead, which cannot change without a commit,
    and a commit is reviewable.
    """
    blob, problem = _committed_blob(repo_root, path)
    if problem:
        return None, problem
    if blob is None:
        return None, None

    proc = _run_git(repo_root, "cat-file", "blob", blob)
    if proc is None or proc.returncode != 0:
        return None, "the committed baseline object could not be read"

    try:
        raw = proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None, "the committed baseline is not valid UTF-8"

    sections, problem = _sections_from_text(raw)
    if problem:
        return None, f"the committed copy of the baseline could not be read: {problem}"
    return sections, None


def _strongest(disk: Sections | None, committed: Sections | None) -> Sections | None:
    """Merge two readings of the predecessor, keeping the higher count per path.

    Weakening either copy has to buy something for an attack on it to be worth
    mounting. Taking the maximum means it buys nothing: the emptied worktree
    copy loses to the committed one, and a committed copy that predates honest
    progress loses to the worktree. A genuine reduction still has the documented
    `--allow-baseline-shrink` way through.
    """
    if disk is None:
        return committed
    if committed is None:
        return disk

    merged: Sections = {name: dict(counts) for name, counts in disk.items()}
    for name, counts in committed.items():
        target = merged.setdefault(name, {})
        for entry, count in counts.items():
            target[entry] = max(target.get(entry, 0), count)
    return merged


def read_previous_sections(
    repo_root: Path, path: Path
) -> tuple[Sections | None, str | None]:
    """Read every counted section of the baseline being replaced.

    Returns `(sections, problem)`. A problem is a reason to refuse the write.
    `(None, None)` means there is genuinely nothing to protect, which is true
    for exactly one case: a baseline that is neither on disk nor in git, so no
    debt has ever been recorded.

    Every other unreadable state fails closed. An absent-but-tracked baseline
    has been deleted, a corrupt one may be mid-merge, and an unreadable one is
    a mystery. Treating any of them as "no predecessor" would let the guard be
    disabled by damaging the very file it protects, which inverts it into a
    tool for laundering a wipe.

    The reading on disk is only ever half the answer. It sits in the working
    tree, so the run asking for the ratchet to move can edit it first, and an
    emptied predecessor agrees to anything. The committed copy is read as well
    and the stronger of the two is what the replacement must beat.
    """
    committed, committed_problem = _committed_sections(repo_root, path)
    if committed_problem:
        return None, committed_problem

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        recorded = _was_recorded(repo_root, path)
        if recorded is None:
            return None, "git could not determine whether branch history recorded the baseline"
        if recorded:
            return None, "git history records the baseline but it is absent from disk"
        return committed, None
    except OSError as exc:
        return None, f"the baseline could not be read ({exc.strerror or exc})"

    disk, problem = _sections_from_text(raw)
    if problem:
        return None, problem
    return _strongest(disk, committed), None
