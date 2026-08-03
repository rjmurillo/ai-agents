"""Differential guard scanner.

Compare two revisions of a guard callable against a shared corpus and report
which findings were added (guard got stronger) and which were removed (guard
lost coverage).

Usage::

    from scripts.guard_diff import load_guard, scan_corpus, diff_findings

    before = load_guard(Path("tests/test_subprocess_text_encoding.py"))
    after  = load_guard(Path("path/to/modified_guard.py"))
    removed_ok = set()  # allowlisted deliberate removals
    removed = diff_findings(scan_corpus(before, Path(".claude/skills")),
                            scan_corpus(after,  Path(".claude/skills")),
                            scan_root=Path(".claude/skills"))[1]
    assert not (removed - removed_ok), f"Guard lost coverage: {removed - removed_ok}"

Finding identity
----------------
A finding is keyed on ``(relative_path, normalized_source_line_text,
occurrence_index)`` rather than ``(relative_path, line_number)``.  Line
numbers shift whenever a line is inserted anywhere above a flagged call; that
shift makes a pure line-number key report false regressions (issue #4286).
The normalized text of the flagged line is stable across such edits: the same
call at a new position produces the same key.

Normalization strips leading and trailing whitespace so that indentation
changes (extracted helper, added nesting level) do not produce spurious diffs.
Two genuinely distinct calls on the same line of the same file map to the same
key; ``occurrence_index`` (0-based) below disambiguates them.

``scan_corpus`` still returns ``dict[str, list[int]]`` (path to line numbers)
for display and backward compatibility.  ``content_findings`` converts that to
the stable ``set[Finding]`` used by ``diff_findings``.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

# (relative_path, normalized_line_text, occurrence_index) -- one detected site.
# occurrence_index disambiguates two findings whose stripped line text is equal
# within the same file.
Finding = tuple[str, str, int]
GuardFn = Callable[[str], list[int]]


def load_guard(guard_path: Path, attr: str = "unpinned_lines") -> GuardFn:
    """Load a guard callable from a Python source file by path.

    Uses a unique module name per path so two calls with different paths do
    not collide in ``sys.modules``.
    """
    spec = importlib.util.spec_from_file_location(
        f"_guard_diff_rev_{abs(hash(str(guard_path.resolve())))}",
        guard_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load guard from {guard_path}")
    mod: ModuleType = importlib.util.module_from_spec(spec)
    # Set __file__ so guards that use Path(__file__) at module scope work.
    mod.__file__ = str(guard_path.resolve())
    spec.loader.exec_module(mod)
    return cast(GuardFn, getattr(mod, attr))


def scan_corpus(guard: GuardFn, scan_root: Path) -> dict[str, list[int]]:
    """Run *guard* on every ``.py`` file under *scan_root*.

    Files that cannot be read or cause *guard* to raise are skipped with a
    diagnostic on stderr; the scan continues.  The returned dict maps each
    relative path that has at least one finding to a sorted list of line
    numbers.
    """
    results: dict[str, list[int]] = {}
    for py_file in sorted(scan_root.rglob("*.py")):
        rel = py_file.relative_to(scan_root).as_posix()
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"guard_diff: skipping {rel} (read error): {exc}", file=sys.stderr)
            continue
        try:
            lines = guard(source)
        except Exception as exc:
            print(f"guard_diff: guard raised on {rel}: {exc}", file=sys.stderr)
            continue
        if lines:
            results[rel] = sorted(lines)
    return results


def content_findings(
    corpus: dict[str, list[int]],
    scan_root: Path,
) -> set[Finding]:
    """Convert a line-number corpus to a set of content-keyed findings.

    Each finding is ``(relative_path, normalized_line_text, occurrence_index)``.
    The normalized text is the flagged source line stripped of leading/trailing
    whitespace.  The occurrence index (0-based) disambiguates two findings with
    identical text within one file.

    Files that cannot be read are skipped silently; a line number beyond the
    end of the file is also skipped (guard and source are from the same scan,
    so this should not happen, but it is not a reason to abort).
    """
    findings: set[Finding] = set()
    for rel, line_numbers in corpus.items():
        try:
            source_lines = (scan_root / rel).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        text_counts: dict[str, int] = {}
        for ln in sorted(line_numbers):
            idx = ln - 1  # convert 1-based line number to 0-based index
            if idx < 0 or idx >= len(source_lines):
                continue
            text = source_lines[idx].strip()
            occ = text_counts.get(text, 0)
            findings.add((rel, text, occ))
            text_counts[text] = occ + 1
    return findings


def diff_findings(
    before: dict[str, list[int]],
    after: dict[str, list[int]],
    scan_root: Path | None = None,
) -> tuple[set[Finding], set[Finding]]:
    """Return ``(added, removed)`` finding sets.

    * ``added``   -- in *after* but not *before*; guard got stronger.
    * ``removed`` -- in *before* but not *after*; guard lost coverage.

    When *scan_root* is provided, findings are keyed on
    ``(path, normalized_line_text, occurrence_index)`` so that a pure line-shift
    (inserting lines above a finding) does not appear as a removal (issue #4286).

    When *scan_root* is ``None``, findings fall back to ``(path, str(lineno), 0)``
    so callers without filesystem access still get a diff, but that diff remains
    line-number-sensitive.
    """
    if scan_root is not None:
        before_flat = content_findings(before, scan_root)
        after_flat = content_findings(after, scan_root)
    else:
        before_flat = {(p, str(ln), 0) for p, lns in before.items() for ln in lns}
        after_flat = {(p, str(ln), 0) for p, lns in after.items() for ln in lns}
    return after_flat - before_flat, before_flat - after_flat


def load_baseline_findings(baseline_path: Path) -> set[Finding]:
    """Load a v2 baseline file and return a set of content-keyed findings.

    The v2 format stores ``findings`` as ``{relative_path: [[text, occ], ...]}``.
    A v1 baseline (``{relative_path: [lineno, ...]}``) cannot be loaded this
    way; use ``content_findings`` with the v1 dict and a scan root instead.
    """
    import json

    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    raw = data.get("findings", {})
    result: set[Finding] = set()
    for rel, entries in raw.items():
        for entry in entries:
            if isinstance(entry, list) and len(entry) == 2:
                text, occ = entry
                result.add((rel, str(text), int(occ)))
    return result
