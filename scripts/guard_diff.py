"""Differential guard scanner.

Compare two revisions of a guard callable against a shared corpus and report
which findings were added (guard got stronger) and which were removed (guard
lost coverage).

Usage::

    from scripts.guard_diff import load_guard, scan_corpus, diff_findings

    before = load_guard(Path("tests/test_subprocess_text_encoding.py"))
    after  = load_guard(Path("/tmp/modified_guard.py"))
    removed_ok = set()  # allowlisted deliberate removals
    removed = diff_findings(scan_corpus(before, Path(".claude/skills")),
                            scan_corpus(after,  Path(".claude/skills")))[1]
    assert not (removed - removed_ok), f"Guard lost coverage: {removed - removed_ok}"
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

# (relative_path, lineno) -- one detected site.
Finding = tuple[str, int]
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


def diff_findings(
    before: dict[str, list[int]],
    after: dict[str, list[int]],
) -> tuple[set[Finding], set[Finding]]:
    """Return ``(added, removed)`` finding sets.

    * ``added``   -- in *after* but not *before*; guard got stronger.
    * ``removed`` -- in *before* but not *after*; guard lost coverage.
    """
    before_flat: set[Finding] = {(p, ln) for p, lns in before.items() for ln in lns}
    after_flat: set[Finding] = {(p, ln) for p, lns in after.items() for ln in lns}
    return after_flat - before_flat, before_flat - after_flat
