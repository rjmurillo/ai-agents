# taste-lint: ignore file-size -- the session corpus scan, the gate tests that
# read it, and the once-per-worker assertion that guards it are one unit; a
# split would put the fixture in a different module from the tests it exists for
# and from the negative control that proves it is not vacuous (issue #5382).
"""Tests for the differential guard scanner (scripts/guard_diff.py).

Coverage:
* ``diff_findings``: positive (one-finding delta), negative (identical dicts),
  edge (overlapping keys, empty dicts).
* ``scan_corpus``: skips unparseable files; reports guard raise without abort.
* ``content_findings``: stable across line shifts (issue #4286).
* Corpus gate: the current guard finds at least everything in the pinned
  baseline, proven against content-keyed identity so a pure line shift cannot
  trigger a false regression (issue #4286).
* Line-shift integration test: inserting a blank line above a flagged call in
  a real corpus file does not fire the gate.
* Negative control: a weakened guard (one rule stubbed out) produces a
  non-empty ``removed`` set, proving the gate goes red on real regressions.

The corpus-gate tests below used to call ``scan_corpus`` against
``.claude/skills`` themselves, four full traversals in all, each one reading and
parsing every ``.py`` file under that root. The scan is invariant for the
duration of a session, so ``corpus_scan`` performs it once per pytest process
and the tests assert against the cached result. Per-file violation diagnostics
are unchanged: every assertion still names the exact findings that moved
(issue #5382).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
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
# One corpus scan per session (issue #5382)
# ---------------------------------------------------------------------------

# Every traversal of the real corpus in this process, appended by the wrapper
# below. Scans of a tmp_path corpus are not repeat passes and are not counted.
_CORPUS_SCANS: list[str] = []


@pytest.fixture(scope="session", autouse=True)
def _count_corpus_scans() -> Iterator[None]:
    """Count real-corpus traversals wherever in this module they are called from.

    Counting executions of the ``corpus_scan`` fixture body instead would assert
    a pytest guarantee: a session fixture already runs at most once per process.
    The wrapper sees a direct ``scan_corpus(guard, CORPUS_ROOT)`` in any test,
    which is the shape the batching regression comes back in.
    """
    import scripts.guard_diff as guard_diff

    original = guard_diff.scan_corpus

    def counting(
        guard: Callable[[str], list[int]], scan_root: Path
    ) -> dict[str, list[int]]:
        if Path(scan_root) == CORPUS_ROOT:
            _CORPUS_SCANS.append(str(scan_root))
        return original(guard, scan_root)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(guard_diff, "scan_corpus", counting)
        yield
    # Order-independent backstop: a scan added by a test that runs after the
    # dedicated assertion below still fails the session.
    assert len(_CORPUS_SCANS) <= 1, (
        f"{CORPUS_ROOT} was traversed {len(_CORPUS_SCANS)} times in this "
        "process. Session-scoped caching regressed."
    )


@dataclass(frozen=True)
class CorpusScan:
    """The real guard's verdict on the corpus, scanned once."""

    results: dict[str, list[int]] = field(default_factory=dict)
    findings: frozenset[tuple[str, str, int]] = frozenset()
    baseline: frozenset[tuple[str, str, int]] = frozenset()


@pytest.fixture(scope="session")
def corpus_scan(_count_corpus_scans: None) -> CorpusScan:
    """Scan ``.claude/skills`` with the real guard once per pytest worker.

    ``scan_corpus`` reads and parses every ``.py`` file under the root, so a
    per-test call multiplies the cost by the number of gate tests. The corpus
    and the guard are both immutable for the session, which makes the result
    safe to share.
    """
    from scripts.guard_diff import content_findings, load_baseline_findings, scan_corpus

    results = scan_corpus(_real_guard(), CORPUS_ROOT)
    return CorpusScan(
        results=results,
        findings=frozenset(content_findings(results, CORPUS_ROOT)),
        baseline=frozenset(load_baseline_findings(BASELINE_PATH)),
    )


# ---------------------------------------------------------------------------
# diff_findings: unit tests
# ---------------------------------------------------------------------------


def test_diff_findings_empty_inputs() -> None:
    from scripts.guard_diff import diff_findings

    added, removed = diff_findings({}, {})
    assert added == set()
    assert removed == set()


def test_diff_findings_identical_dicts_produce_empty_diff(tmp_path: Path) -> None:
    """Negative case: identical before/after -> no diff."""
    from scripts.guard_diff import diff_findings

    py = tmp_path / "a.py"
    py.write_text("subprocess.run(cmd)\nsubprocess.run(other)\n", encoding="utf-8")
    corpus = {"a.py": [1, 2]}
    added, removed = diff_findings(corpus, corpus, scan_root=tmp_path)
    assert added == set()
    assert removed == set()


def test_diff_findings_one_added_finding(tmp_path: Path) -> None:
    """A finding in after but not before appears in added."""
    from scripts.guard_diff import diff_findings

    py = tmp_path / "a.py"
    py.write_text("subprocess.run(cmd)\nsubprocess.run(other)\n", encoding="utf-8")
    before = {"a.py": [1]}
    after = {"a.py": [1, 2]}
    added, removed = diff_findings(before, after, scan_root=tmp_path)
    assert any(f[1] == "subprocess.run(other)" for f in added)
    assert removed == set()


def test_diff_findings_one_removed_finding(tmp_path: Path) -> None:
    """Positive case: a finding in before but not after appears in removed."""
    from scripts.guard_diff import diff_findings

    py = tmp_path / "a.py"
    py.write_text("subprocess.run(cmd)\nsubprocess.run(other)\n", encoding="utf-8")
    before = {"a.py": [1, 2]}
    after = {"a.py": [1]}
    added, removed = diff_findings(before, after, scan_root=tmp_path)
    assert any(f[1] == "subprocess.run(other)" for f in removed)
    assert added == set()


def test_diff_findings_entire_file_removed(tmp_path: Path) -> None:
    """A file disappearing from after puts all its lines in removed."""
    from scripts.guard_diff import diff_findings

    py = tmp_path / "gone.py"
    py.write_text("a()\nb()\nc()\n", encoding="utf-8")
    before = {"gone.py": [1, 2, 3]}
    after: dict[str, list[int]] = {}
    added, removed = diff_findings(before, after, scan_root=tmp_path)
    assert len(removed) == 3
    assert added == set()


def test_diff_findings_entire_file_added(tmp_path: Path) -> None:
    """A file appearing only in after puts all its lines in added."""
    from scripts.guard_diff import diff_findings

    py = tmp_path / "new.py"
    py.write_text("x()\ny()\n", encoding="utf-8")
    before: dict[str, list[int]] = {}
    after = {"new.py": [1, 2]}
    added, removed = diff_findings(before, after, scan_root=tmp_path)
    assert len(added) == 2
    assert removed == set()


# ---------------------------------------------------------------------------
# content_findings: stable under line shifts (issue #4286)
# ---------------------------------------------------------------------------


def test_diff_findings_line_shift_does_not_fire(tmp_path: Path) -> None:
    """Inserting a blank line above a flagged call must not produce a removal.

    This is the decisive test for issue #4286: a pure position shift of an
    unchanged call cannot read as lost coverage.
    """
    from scripts.guard_diff import content_findings

    # "Before" state: flagged call at line 3.
    before_src = "# comment\n# comment\nsubprocess.run(cmd)\n"
    py = tmp_path / "skill.py"
    py.write_text(before_src, encoding="utf-8")
    before_corpus = {"skill.py": [3]}
    before_set = content_findings(before_corpus, tmp_path)

    # "After" state: blank line inserted before the call; it is now at line 4.
    after_src = "# comment\n# comment\n\nsubprocess.run(cmd)\n"
    py.write_text(after_src, encoding="utf-8")
    after_corpus = {"skill.py": [4]}
    after_set = content_findings(after_corpus, tmp_path)

    assert before_set == after_set, (
        "Line shift changed the finding identity; content-keyed diff "
        "should produce the same set regardless of position."
    )


def test_diff_findings_genuine_removal_still_fires(tmp_path: Path) -> None:
    """A finding whose source line text disappears must remain in removed."""
    from scripts.guard_diff import content_findings

    py = tmp_path / "a.py"
    # "Before" state: two calls.
    py.write_text("subprocess.run(cmd)\nsubprocess.run(other)\n", encoding="utf-8")
    before = {"a.py": [1, 2]}
    before_set = content_findings(before, tmp_path)

    # "After" state: second call deleted.
    py.write_text("subprocess.run(cmd)\n", encoding="utf-8")
    after = {"a.py": [1]}
    after_set = content_findings(after, tmp_path)

    removed = before_set - after_set
    assert any(f[1] == "subprocess.run(other)" for f in removed), (
        "A call that was genuinely deleted must still appear in removed."
    )


def test_content_findings_identical_text_two_occurrences(tmp_path: Path) -> None:
    """Two findings with the same stripped text get distinct occurrence indices."""
    from scripts.guard_diff import content_findings

    py = tmp_path / "a.py"
    py.write_text("subprocess.run(cmd)\nsubprocess.run(cmd)\n", encoding="utf-8")
    corpus = {"a.py": [1, 2]}
    result = content_findings(corpus, tmp_path)
    assert ("a.py", "subprocess.run(cmd)", 0) in result
    assert ("a.py", "subprocess.run(cmd)", 1) in result
    assert len(result) == 2


# ---------------------------------------------------------------------------
# scan_corpus: edge cases
# ---------------------------------------------------------------------------


def test_scan_corpus_skips_unparseable_file(tmp_path: Path) -> None:
    """A file with a syntax error is skipped; remaining files are still scanned."""
    from scripts.guard_diff import scan_corpus

    bad = tmp_path / "bad.py"
    bad.write_text("def (: pass\n", encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text("# nothing flagged here\n", encoding="utf-8")

    sentinel_found: list[str] = []

    def guard_that_parses(source: str) -> list[int]:
        import ast

        ast.parse(source)  # will raise on bad.py
        sentinel_found.append(source)
        return []

    scan_corpus(guard_that_parses, tmp_path)
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
    assert any("# b" in v for v in visited)
    assert results.get("b.py") == [1]
    assert "a.py" not in results


def test_scan_corpus_empty_dir_returns_empty(tmp_path: Path) -> None:
    from scripts.guard_diff import scan_corpus

    results = scan_corpus(lambda src: [], tmp_path)
    assert results == {}


# ---------------------------------------------------------------------------
# Corpus gate: real guard vs pinned baseline (content-keyed, issue #4286)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_gate_current_guard_finds_all_baseline_findings(
    corpus_scan: CorpusScan,
) -> None:
    """The current guard must report at least every finding in the pinned baseline.

    Findings are compared by content (normalized source line text + occurrence
    index) rather than by line number.  A pure line shift does not trigger a
    false regression (issue #4286).  To legitimately remove a finding, update
    ``tests/fixtures/guard_corpus_baseline.json`` and explain why in the
    commit message.
    """
    removed = corpus_scan.baseline - corpus_scan.findings
    assert removed == set(), (
        "Guard lost coverage: the following findings were in the baseline but "
        "are no longer reported by the current guard.\n"
        "If this removal is intentional (a false-positive fix), update "
        "tests/fixtures/guard_corpus_baseline.json and explain why.\n"
        f"Missing: {sorted(removed)}"
    )


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_gate_reports_no_finding_the_baseline_does_not_carry(
    corpus_scan: CorpusScan,
) -> None:
    """A new unpinned call must fail here, not be written into the baseline.

    The removed-only assertion above is one-directional: it catches a guard that
    stopped detecting, and says nothing about a script that started offending.
    A branch could add two unpinned subprocess calls, add both line numbers to
    the baseline, and pass. Measured clean at the head of this branch: 0 added,
    0 removed across the whole corpus.
    """
    added = corpus_scan.findings - corpus_scan.baseline

    assert added == set(), (
        "New unpinned subprocess text=True call(s). Pass encoding=\"utf-8\" (or "
        "read bytes) instead of adding the line to the baseline.\n"
        f"Added: {sorted(added)}"
    )


# ---------------------------------------------------------------------------
# Line-shift integration test using real corpus (issue #4286)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_gate_survives_line_insertion_in_flagged_file(
    tmp_path: Path,
) -> None:
    """Inserting a blank line above a real corpus finding must not fire the gate.

    Picks the first file with findings from the baseline, copies it to a
    scratch tree, prepends a blank line, re-scans with the same guard, and
    asserts content_findings produces the same set before and after.  This is
    the decisive integration test for issue #4286.
    """
    from scripts.guard_diff import content_findings, load_baseline_findings, scan_corpus

    baseline_set = load_baseline_findings(BASELINE_PATH)
    guard = _real_guard()

    # Find a baseline file that actually exists under CORPUS_ROOT.
    raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    victim_rel = next(
        rel for rel in raw["findings"] if (CORPUS_ROOT / rel).exists()
    )

    # Build a scratch corpus root containing only the victim file.
    scratch = tmp_path / "skills"
    victim_copy = scratch / victim_rel
    victim_copy.parent.mkdir(parents=True, exist_ok=True)

    original = (CORPUS_ROOT / victim_rel).read_text(encoding="utf-8")
    victim_copy.write_text(original, encoding="utf-8")

    before = scan_corpus(guard, scratch)
    before_set = content_findings(before, scratch)

    # Insert a blank line at the top, shifting every finding down by one.
    victim_copy.write_text("\n" + original, encoding="utf-8")
    after = scan_corpus(guard, scratch)
    after_set = content_findings(after, scratch)

    assert before_set == after_set, (
        f"Line insertion triggered a finding identity change for {victim_rel!r}. "
        f"Before: {sorted(before_set)}  After: {sorted(after_set)}"
    )
    _ = baseline_set  # used to ensure baseline is loadable


# ---------------------------------------------------------------------------
# Negative control: prove the gate goes red when a rule is removed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_gate_catches_weakened_guard(corpus_scan: CorpusScan) -> None:
    """Negative control: a guard that drops one file's findings trips the gate.

    This proves the gate is not vacuous.  We weaken the cached scan the way a
    guard that stopped reporting the victim's lines would have weakened it, run
    the diff, and assert the removed set is non-empty.  We then verify that the
    full guard produces an empty removed set (gate goes green).

    ``scan_corpus`` maps the guard over each file independently, so filtering
    the cached per-file line lists is identical to rescanning the corpus with
    the weakened guard, without a second traversal (issue #5382).
    """
    # Pick the first file with at least one finding as the victim.
    raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    victim_file = next(iter(raw["findings"]))
    victim_lines = set(corpus_scan.results.get(victim_file, []))

    weakened_results = {
        rel: kept
        for rel, lines in corpus_scan.results.items()
        if (kept := [ln for ln in lines if ln not in victim_lines])
    }

    from scripts.guard_diff import content_findings

    weakened_set = content_findings(weakened_results, CORPUS_ROOT)
    removed_w = corpus_scan.baseline - weakened_set
    assert removed_w, (
        "Negative control failed: weakened guard did not trigger the gate. "
        f"Victim file: {victim_file!r}"
    )

    # Green path: real guard produces no removals.
    removed_f = corpus_scan.baseline - corpus_scan.findings
    assert removed_f == set(), (
        f"Unexpected: real guard triggered the gate. Removed: {removed_f}"
    )


@pytest.mark.skipif(
    not CORPUS_ROOT.exists(),
    reason=".claude/skills not present",
)
def test_corpus_is_scanned_once_per_worker(corpus_scan: CorpusScan) -> None:
    """The gate tests share one traversal, not one traversal each.

    Before issue #5382 the three gate tests above ran four ``scan_corpus`` passes
    over ``.claude/skills`` between them. Session scope collapses that to one per
    pytest process, which is also what an xdist worker gets. The counter comes
    from a wrapper around ``scan_corpus`` itself, so a gate test that goes back
    to scanning the corpus directly fails here even though it never touches the
    fixture.
    """
    assert corpus_scan.results
    assert _CORPUS_SCANS == [str(CORPUS_ROOT)], (
        f"{CORPUS_ROOT} was traversed {len(_CORPUS_SCANS)} times in this "
        "process, not once. Session-scoped caching regressed."
    )
