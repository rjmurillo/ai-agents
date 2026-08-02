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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.validation.portability_git import (
    committed_blob,
    run_git,
    was_recorded,
)

Sections = dict[str, dict[str, int]]

COUNTED_SECTIONS = ("files", "marker_files")
"""Every baseline section that records a count somebody can regress.

`files` counts violations, where lower is better. `marker_files` counts
suppressed references, where the value must stay exact. Both are debt records,
so both need the same protection; guarding only the first leaves a writable
hole in the same artifact.
"""


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


def _committed_sections(repo_root: Path, path: Path) -> tuple[Sections | None, str | None]:
    """Read the baseline as HEAD records it, the one copy an edit cannot reach.

    Every other witness to the old debt lives in the working tree, where the
    same run that wants the ratchet lowered can rewrite it first. `git show`
    reads the committed object instead, which cannot change without a commit.

    What that buys, stated exactly, because it is narrower than it sounds. The
    floor makes a lowering land in a diff. It is not an authorization boundary.
    `--allow-baseline-shrink` lowers the count deliberately and is meant to, and
    anyone who can run this can also run that, so local git state is trusted
    here: HEAD, the object database, and `.git` generally. Forging them costs
    more than the documented flag and produces the same reviewable diff.

    The diff is therefore the whole asset, which is why
    `refuse_undiffable_baseline` guards it separately. Refs #4244.
    """
    blob, problem = committed_blob(repo_root, path)
    if problem:
        return None, problem
    if blob is None:
        return None, None

    proc = run_git(repo_root, "cat-file", "blob", blob)
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
        recorded = was_recorded(repo_root, path)
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
