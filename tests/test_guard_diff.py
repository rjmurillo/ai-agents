"""Tests for the differential guard scanner (scripts/guard_diff.py).

Coverage:
* ``diff_findings``: positive (one-finding delta), negative (identical dicts),
  edge (overlapping keys, empty dicts).
* ``scan_corpus``: skips unparseable files; reports guard raise without abort.
* Corpus gate: the current guard finds at least everything in the pinned
  baseline, proving that no detection has silently vanished.
* Negative control: a weakened guard (one rule stubbed out) produces a
  non-empty ``removed`` set, proving the gate goes red on real regressions.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "tests" / "test_subprocess_text_encoding.py"
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "guard_corpus_baseline.json"
CORPUS_ROOT = REPO_ROOT / ".claude" / "skills"


def _load_module_attr(path: Path, attr: str) -> object:
    import importlib.util
    import types

    spec = importlib.util.spec_from_file_location(
        f"_test_guard_diff_helper_{abs(hash(str(path.resolve())))}", path
    )
    assert spec is not None
    assert spec.loader is not None
    mod = types.ModuleType(spec.name)
    mod.__file__ = str(path.resolve())
    spec.loader.exec_module(mod)
    return getattr(mod, attr)


def _real_guard() -> Callable[[str], list[int]]:
    from typing import cast

    return cast(Callable[[str], list[int]], _load_module_attr(GUARD_PATH, "unpinned_lines"))


# ---------------------------------------------------------------------------
# diff_findings: unit tests
# ---------------------------------------------------------------------------


def test_diff_findings_empty_inputs() -> None:
    from scripts.guard_diff import diff_findings

    added, removed = diff_findings({}, {})
    assert added == set()
    assert removed == set()


def test_diff_findings_identical_dicts_produce_empty_diff() -> None:
    """Negative case: identical before/after -> no diff."""
    from scripts.guard_diff import diff_findings

    corpus = {"a.py": [10, 20], "b.py": [5]}
    added, removed = diff_findings(corpus, corpus)
    assert added == set()
    assert removed == set()


def test_diff_findings_one_added_finding() -> None:
    """A finding in after but not before appears in added."""
    from scripts.guard_diff import diff_findings

    before = {"a.py": [10]}
    after = {"a.py": [10, 20]}
    added, removed = diff_findings(before, after)
    assert ("a.py", 20) in added
    assert removed == set()


def test_diff_findings_one_removed_finding() -> None:
    """Positive case: a finding in before but not after appears in removed."""
    from scripts.guard_diff import diff_findings

    before = {"a.py": [10, 20]}
    after = {"a.py": [10]}
    added, removed = diff_findings(before, after)
    assert ("a.py", 20) in removed
    assert added == set()


def test_diff_findings_entire_file_removed() -> None:
    """A file disappearing from after puts all its lines in removed."""
    from scripts.guard_diff import diff_findings

    before = {"gone.py": [1, 2, 3]}
    after: dict[str, list[int]] = {}
    added, removed = diff_findings(before, after)
    assert removed == {("gone.py", 1), ("gone.py", 2), ("gone.py", 3)}
    assert added == set()


def test_diff_findings_entire_file_added() -> None:
    """A file appearing only in after puts all its lines in added."""
    from scripts.guard_diff import diff_findings

    before: dict[str, list[int]] = {}
    after = {"new.py": [7, 14]}
    added, removed = diff_findings(before, after)
    assert added == {("new.py", 7), ("new.py", 14)}
    assert removed == set()


# ---------------------------------------------------------------------------
# scan_corpus: edge cases
# ---------------------------------------------------------------------------


def test_scan_corpus_skips_unparseable_file(tmp_path: Path) -> None:
    """A file with a syntax error is skipped; remaining files are still scanned."""
    from scripts.guard_diff import scan_corpus

    bad = tmp_path / "bad.py"
    bad.write_text("def (: pass\n", encoding="utf-8")
    good = tmp_path / "good.py"
    # This guard just echoes the line if the source contains a sentinel.
    good.write_text("# nothing flagged here\n", encoding="utf-8")

    sentinel_found: list[str] = []

    def guard_that_parses(source: str) -> list[int]:
        import ast

        ast.parse(source)  # will raise on bad.py
        sentinel_found.append(source)
        return []

    scan_corpus(guard_that_parses, tmp_path)
    # good.py was visited; bad.py was skipped without abort
    assert any("# nothing flagged here" in s for s in sentinel_found)


def test_scan_corpus_guard_raise_does_not_abort(tmp_path: Path) -> None:
    """A guard that raises on one file does not abort the rest of the scan."""
    from scripts.guard_diff import scan_corpus

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("# a\n", encoding="utf-8")
    b.write_text("# b\n", encoding="utf-8")

    visited: list[str] = []

    def flaky(source: str) -> list[int]:
        visited.append(source)
        if "# a" in source:
            raise RuntimeError("boom")
        return [1]

    results = scan_corpus(flaky, tmp_path)
    # a.py raised, b.py did not; b.py's finding survives
    assert any("# b" in v for v in visited)
    assert results.get("b.py") == [1]
    assert "a.py" not in results


def test_scan_corpus_empty_dir_returns_empty(tmp_path: Path) -> None:
    from scripts.guard_diff import scan_corpus

    results = scan_corpus(lambda src: [], tmp_path)
    assert results == {}


# ---------------------------------------------------------------------------
# Corpus gate: real guard vs pinned baseline
# ---------------------------------------------------------------------------


def _load_baseline() -> dict[str, list[int]]:
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return data["findings"]


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_gate_current_guard_finds_all_baseline_findings() -> None:
    """The current guard must report at least every finding in the pinned baseline.

    This is the differential gate: if a detection rule silently disappears, a
    finding that was in the baseline will no longer appear in the current
    output, and this test fails.  To legitimately remove a finding, update
    ``tests/fixtures/guard_corpus_baseline.json`` and explain why in the
    commit message.
    """
    from scripts.guard_diff import diff_findings, scan_corpus

    guard = _real_guard()
    baseline = _load_baseline()
    current = scan_corpus(guard, CORPUS_ROOT)
    _added, removed = diff_findings(baseline, current)

    assert removed == set(), (
        "Guard lost coverage: the following findings were in the baseline but "
        "are no longer reported by the current guard.\n"
        "If this removal is intentional (a false-positive fix), update "
        "tests/fixtures/guard_corpus_baseline.json and explain why.\n"
        f"Missing: {sorted(removed)}"
    )


# ---------------------------------------------------------------------------
# Negative control: prove the gate goes red when a rule is removed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_gate_catches_weakened_guard() -> None:
    """Negative control: a guard that drops one file's findings trips the gate.

    This proves the gate is not vacuous.  We build a weakened guard that
    returns [] for one specific file the baseline knows about, run the diff,
    and assert the removed set is non-empty.  We then verify that the full
    guard produces an empty removed set (gate goes green).
    """
    from scripts.guard_diff import diff_findings, scan_corpus

    baseline = _load_baseline()
    # Pick the first file with at least one finding as the victim.
    victim_file = next(iter(baseline))
    real_guard = _real_guard()

    def weakened_guard(source: str) -> list[int]:
        lines = real_guard(source)
        # Wipe findings for the victim by recognising a marker we embed in the
        # wrapper -- but since we cannot inspect the filename inside the guard
        # callable, we compare line numbers instead: suppress everything from
        # the victim so the set differs.  In practice we just return [] for
        # any source that would produce the victim's line numbers.
        victim_lines = baseline[victim_file]
        if set(lines) & set(victim_lines):
            return [ln for ln in lines if ln not in victim_lines]
        return lines

    weakened_results = scan_corpus(weakened_guard, CORPUS_ROOT)
    _added_w, removed_w = diff_findings(baseline, weakened_results)
    assert removed_w, (
        "Negative control failed: weakened guard did not trigger the gate. "
        f"Victim file: {victim_file!r}"
    )

    # Green path: real guard produces no removals.
    full_results = scan_corpus(real_guard, CORPUS_ROOT)
    _added_f, removed_f = diff_findings(baseline, full_results)
    assert removed_f == set(), f"Unexpected: real guard triggered the gate. Removed: {removed_f}"
