"""Baseline artifact lifecycle for the portability ratchets.

Tree coverage asks whether the scan saw everything it was supposed to see.
This module asks the other half of the question: whether the artifact about to
be destroyed agrees that its replacement is an improvement, and whether that
replacement lands without collateral damage.

The two halves are separate because they fail differently. Coverage reasons
about the world, which is unbounded, so it can always be lied to by a tree
nobody thought of. The artifact comparison reasons about one file whose
contents are already known, so its blind spots are enumerable. Keeping them
apart makes the second one auditable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def _is_tracked(repo_root: Path, path: Path) -> bool:
    """Report whether git has the baseline, so absence can be told from loss."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z", "--", str(rel)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip("\0").strip())


def _coerce_counts(section: object, name: str) -> tuple[dict[str, int] | None, str | None]:
    """Convert one baseline section to counts, reporting why it is unusable."""
    if not isinstance(section, dict):
        return None, f"section {name!r} is not a JSON object"
    counts: dict[str, int] = {}
    for key, value in section.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            return None, f"the count for {key!r} in {name!r} is not an integer"
    return counts, None


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
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if _is_tracked(repo_root, path):
            return None, "git tracks the baseline but it is absent from disk"
        return None, None
    except OSError as exc:
        return None, f"the baseline could not be read ({exc.strerror or exc})"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the baseline is not valid JSON ({exc.msg}, line {exc.lineno})"
    if not isinstance(data, dict):
        return None, "the baseline is not a JSON object"

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


def _regressions(previous: Mapping[str, int], current: Mapping[str, int]) -> list[str]:
    """List paths the replacement drops or under-counts, worst first."""
    losses: list[tuple[int, str]] = []
    for path, was in previous.items():
        now = current.get(path)
        if now is None:
            losses.append((was, f"{path} (dropped, was {was})"))
        elif now < was:
            losses.append((was - now, f"{path} ({was} -> {now})"))
    return [text for _, text in sorted(losses, key=lambda item: (-item[0], item[1]))]


def refuse_dropped_entries(
    previous: Sections | None,
    current: Mapping[str, Mapping[str, int]],
    unit: str,
    allow_shrink: bool,
    problem: str | None = None,
) -> bool:
    """Refuse a write that records less debt than the baseline it replaces.

    Every coverage probe reasons about the tree. This one reasons about the
    artifact being destroyed, which is the thing the hazard is measured in. A
    partial scan, an index arranged to agree with a truncated disk, a file
    replaced by a directory, and a root that was never enumerated all converge
    on one observable: the replacement records less than its predecessor.

    Less means either fewer paths or a smaller count for the same path. A
    symlink swap keeps the path and empties the count, so a key-set comparison
    alone would wave it through.

    A reduction is legitimate when a file is deliberately removed or its
    violations are fixed, so the escape exists. It has to be named, because a
    destructive default is what turned each earlier version of this guard into
    a wipe.
    """
    if problem:
        print(
            f"Refusing to write a baseline because the one it would replace cannot "
            f"be trusted: {problem}. The existing baseline is the only record of "
            "what is already forgiven, so overwriting it while it is unreadable "
            "would discard that record silently. Restore it from git, then rerun.",
            file=sys.stderr,
        )
        return True
    if previous is None or allow_shrink:
        return False

    for name in sorted(previous):
        losses = _regressions(previous[name], current.get(name, {}))
        if not losses:
            continue
        shown = ", ".join(losses[:5])
        more = f", and {len(losses) - 5} more" if len(losses) > 5 else ""
        scope = unit if name == "files" else f"suppression records in {name}"
        print(
            f"Refusing to write a baseline that reduces {len(losses)} of "
            f"{len(previous[name])} recorded {scope}: {shown}{more}. The baseline "
            "is the only record of those violations, so reducing an entry forgives "
            "it permanently. If the reduction is deliberate, rerun with "
            "--allow-baseline-shrink.",
            file=sys.stderr,
        )
        return True
    return False


def refuse_symlinked_baseline(baseline_path: Path) -> bool:
    """Refuse to write through a symlink at the baseline path.

    Following one writes outside the path git tracks. The target is not the
    ratchet's to overwrite, and a checkout that produced a symlink here is not
    a checkout whose scan can be trusted.
    """
    if not baseline_path.is_symlink():
        return False
    print(
        f"Refusing to write a baseline through a symlink: {baseline_path}. "
        "Following it would write outside the path git tracks, and the file it "
        "points at is not the ratchet's to overwrite.",
        file=sys.stderr,
    )
    return True


def write_baseline_json(
    repo_root: Path,
    baseline_path: Path,
    payload: Mapping[str, Any],
    counted: Mapping[str, Mapping[str, int]],
    unit: str,
    allow_shrink: bool,
) -> int:
    """Write the baseline atomically, re-checking the predecessor as it lands.

    The predecessor is read twice: once by the caller, for an early refusal
    with a clear message, and once here, immediately before the replacement.
    The second read is what makes a concurrent writer observable. Truncating
    the baseline mid-scan used to make it look like there was nothing to
    protect, which turned a race into a wipe.

    Writing through a sibling temporary file and one `os.replace` keeps the
    artifact whole for every reader, and replaces a symlink at the destination
    rather than following it out of the repository.
    """
    if refuse_symlinked_baseline(baseline_path):
        return 2

    previous, problem = read_previous_sections(repo_root, baseline_path)
    if refuse_dropped_entries(previous, counted, unit, allow_shrink, problem):
        return 2

    text = json.dumps(payload, indent=2) + "\n"
    tmp = baseline_path.with_name(f"{baseline_path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, baseline_path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        print(f"Could not write baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2
    return 0
