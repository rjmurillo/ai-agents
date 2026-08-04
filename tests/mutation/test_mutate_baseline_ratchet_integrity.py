"""Mutation harness for baseline/ratchet integrity fixes (Issues #4493, #4494).

Covers three mutants in the changed source:
  M1 -- portability_common.load_baseline: mutate isinstance check to exclude bool
         (makes bool counts slip through as valid integers)
  M2 -- portability_baseline.refuse_diff_suppressed_baseline: mutate "unset" to "set"
         (makes the guard trigger on "set" instead of "unset")
  M2b -- portability_baseline: flip None check to fail-open
  M3 -- check_skill_md_exec_portability.scan_all: mutate SCAN_ROOTS reference
         (breaks single-traversal guarantee; anchored on the two-line block unique
          to scan_all to avoid the ambiguity that caused DID-NOT-APPLY in #4493)

Each mutant is:
  - counted in the source before patching (DID-NOT-APPLY detection)
  - applied in a pytest fixture teardown, suite run, result classified
  - restored and verified with cmp -s against a backup

One inverted control asserts rc == 0 (suite SURVIVES a benign mutation).
All test files are referenced by filesystem path, never dotted module name.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO_ROOT / "scripts" / "validation"
TESTS = REPO_ROOT / "tests" / "validation"

TEST_PATH = str(TESTS / "test_baseline_ratchet_integrity.py")


def _run_suite(*extra_paths: str) -> subprocess.CompletedProcess[str]:
    """Run pytest on the integrity test file plus optional extra paths."""
    paths = [TEST_PATH, *extra_paths]
    return subprocess.run(
        ["uv", "run", "--frozen", "python", "-m", "pytest", *paths, "-q", "--tb=short"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )


def _classify(proc: subprocess.CompletedProcess[str]) -> str:
    if proc.returncode == 4:
        return "HARNESS-ERROR: pytest exit 4 (no tests ran via path)"
    if "no tests ran" in proc.stdout.lower() or "no tests ran" in proc.stderr.lower():
        return "HARNESS-ERROR: no tests ran"
    if proc.returncode == 0:
        return "SURVIVED"
    return "DEAD"


def _count_occurrences(path: Path, pattern: str) -> int:
    return path.read_text().count(pattern)


@pytest.fixture()
def _backup(tmp_path: Path):
    """Context manager that saves/restores a file around a mutation.

    Usage::

        with _backup(target_path, tmp_path) as bak:
            target_path.write_text(mutated_text)
            ...
    """
    # Yielded as a factory so each test can call it with the path it needs.
    saved: list[tuple[Path, Path]] = []

    class _Guard:
        def __init__(self, path: Path) -> None:
            self._path = path
            bak = tmp_path / (path.name + ".bak")
            shutil.copy2(path, bak)
            saved.append((path, bak))

        def __enter__(self) -> _Guard:
            return self

        def __exit__(self, *_: object) -> None:
            path, bak = saved[-1]
            shutil.copy2(bak, path)

    yield _Guard


def _apply_mutation(path: Path, old: str, new: str, backup: Path) -> bool:
    """Apply a mutation. Returns False when the pattern is absent (DID-NOT-APPLY)."""
    text = path.read_text()
    if old not in text:
        return False
    shutil.copy2(path, backup)
    path.write_text(text.replace(old, new, 1))
    return True


def _restore(path: Path, backup: Path) -> None:
    shutil.copy2(backup, path)
    assert path.read_bytes() == backup.read_bytes(), "restore check failed: bytes differ"
    backup.unlink()


# ---------------------------------------------------------------------------
# Test functions (one per mutant)
# ---------------------------------------------------------------------------


def test_m1_bool_check_is_dead(tmp_path: Path) -> None:
    """M1: weaken bool rejection so bool values slip through as integers."""
    target = SCRIPTS / "portability_common.py"
    pattern = "not isinstance(value, int) or isinstance(value, bool)"
    count = _count_occurrences(target, pattern)
    assert count > 0, f"M1-bool-check DID-NOT-APPLY: pattern absent in {target}"
    assert count == 1, f"M1-bool-check PATTERN-AMBIGUOUS: {count} occurrences"

    backup = tmp_path / "portability_common.py.bak"
    applied = _apply_mutation(target, pattern, "not isinstance(value, int)", backup)
    assert applied, "M1-bool-check: replace had no effect"

    try:
        proc = _run_suite()
        result = _classify(proc)
    finally:
        _restore(target, backup)

    assert result not in ("HARNESS-ERROR: pytest exit 4", "HARNESS-ERROR: no tests ran"), (
        f"M1: harness error: {result}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert result == "DEAD", (
        f"M1-bool-check SURVIVED (expected DEAD).\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_m2_diff_attr_guard_is_dead(tmp_path: Path) -> None:
    """M2: swap 'unset' for 'set' in the diff-attribute guard."""
    target = SCRIPTS / "portability_baseline.py"
    pattern = 'if attr != "unset":'
    count = _count_occurrences(target, pattern)
    assert count > 0, f"M2-diff-attr-guard DID-NOT-APPLY: pattern absent in {target}"
    assert count == 1, f"M2-diff-attr-guard PATTERN-AMBIGUOUS: {count} occurrences"

    backup = tmp_path / "portability_baseline.py.bak"
    applied = _apply_mutation(target, pattern, 'if attr != "set":', backup)
    assert applied, "M2-diff-attr-guard: replace had no effect"

    try:
        proc = _run_suite()
        result = _classify(proc)
    finally:
        _restore(target, backup)

    assert result not in ("HARNESS-ERROR: pytest exit 4", "HARNESS-ERROR: no tests ran"), (
        f"M2: harness error: {result}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert result == "DEAD", (
        f"M2-diff-attr-guard SURVIVED (expected DEAD).\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_m2b_diff_attr_none_guard_is_dead(tmp_path: Path) -> None:
    """M2b: flip None check to fail-open (contradicts fail-closed spec)."""
    target = SCRIPTS / "portability_baseline.py"
    pattern = "    if attr is None:\n"
    count = _count_occurrences(target, pattern)
    assert count > 0, f"M2b DID-NOT-APPLY: pattern absent in {target}"
    assert count == 1, f"M2b PATTERN-AMBIGUOUS: {count} occurrences"

    backup = tmp_path / "portability_baseline_none.py.bak"
    applied = _apply_mutation(target, pattern, "    if attr is not None:\n", backup)
    assert applied, "M2b: replace had no effect"

    try:
        proc = _run_suite()
        result = _classify(proc)
    finally:
        _restore(target, backup)

    assert result not in ("HARNESS-ERROR: pytest exit 4", "HARNESS-ERROR: no tests ran"), (
        f"M2b: harness error: {result}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert result == "DEAD", (
        f"M2b SURVIVED (expected DEAD).\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_m3_scan_all_roots_is_dead(tmp_path: Path) -> None:
    """M3: drop the SCAN_ROOTS loop in scan_all (empty all result dicts).

    The anchor is a two-line block unique to scan_all, avoiding the ambiguity
    that caused DID-NOT-APPLY when the single-line anchor matched twice (#4493).
    """
    target = SCRIPTS / "check_skill_md_exec_portability.py"
    # The two-line anchor exists only in scan_all, not in scan_dangling_skill_relative_scripts.
    old = (
        "    for parts in SCAN_ROOTS:\n"
        '        root_name = "/".join(parts)\n'
    )
    new = (
        "    for parts in []:\n"
        '        root_name = "/".join(parts)\n'
    )
    count = _count_occurrences(target, old)
    assert count > 0, f"M3-scan-all-roots DID-NOT-APPLY: two-line anchor absent in {target}"
    assert count == 1, f"M3-scan-all-roots PATTERN-AMBIGUOUS: {count} occurrences"

    backup = tmp_path / "check_skill_md_exec.py.bak"
    applied = _apply_mutation(target, old, new, backup)
    assert applied, "M3-scan-all-roots: replace had no effect"

    try:
        proc = _run_suite()
        result = _classify(proc)
    finally:
        _restore(target, backup)

    assert result not in ("HARNESS-ERROR: pytest exit 4", "HARNESS-ERROR: no tests ran"), (
        f"M3: harness error: {result}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert result == "DEAD", (
        f"M3-scan-all-roots SURVIVED (expected DEAD).\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_m4_inverted_control_survives(tmp_path: Path) -> None:
    """Inverted control: a benign change must SURVIVE (harness sanity check).

    Changes an unrelated comment in portability_common.py. The suite must
    pass (rc == 0) after this mutation. If it does not, the harness or tests
    are broken, not the production code.
    """
    target = SCRIPTS / "portability_common.py"
    pattern = '"""Read and validate a portability ratchet baseline."""'
    count = _count_occurrences(target, pattern)
    assert count > 0, f"M4-inverted-ctrl DID-NOT-APPLY: pattern absent in {target}"
    assert count == 1, f"M4-inverted-ctrl PATTERN-AMBIGUOUS: {count} occurrences"

    backup = tmp_path / "portability_common_ctrl.py.bak"
    applied = _apply_mutation(
        target,
        pattern,
        '"""Read and validate a portability ratchet baseline. (benign)"""',
        backup,
    )
    assert applied, "M4-inverted-ctrl: replace had no effect"

    try:
        proc = _run_suite()
        result = _classify(proc)
    finally:
        _restore(target, backup)

    assert result not in ("HARNESS-ERROR: pytest exit 4", "HARNESS-ERROR: no tests ran"), (
        f"M4: harness error: {result}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert result == "SURVIVED", (
        f"M4-inverted-ctrl FAILED (expected SURVIVED, got {result}).\n"
        f"The harness or tests are broken.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
