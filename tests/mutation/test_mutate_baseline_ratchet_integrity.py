"""Mutation harness for baseline/ratchet integrity fixes.

Covers three mutants in the changed source:
  M1 -- portability_common.load_baseline: mutate isinstance check to exclude bool
         (makes bool counts slip through as valid integers)
  M2 -- portability_baseline.refuse_diff_suppressed_baseline: mutate "unset" to "set"
         (makes the guard trigger on "set" instead of "unset")
  M3 -- check_skill_md_exec_portability.scan_all: mutate SCAN_ROOTS reference
         (breaks single-traversal guarantee)

Each mutant is:
  - counted in the source before patching (DID-NOT-APPLY detection)
  - applied, suite run, result classified
  - restored and verified with cmp -s against a backup

One inverted control asserts rc == 0 (suite SURVIVES a benign mutation).
All test files are referenced by filesystem path, never dotted module name.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

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


def mutant_m1_bool_check(tmp_path: Path) -> str:
    """M1: weaken bool rejection so bool values slip through as integers."""
    target = SCRIPTS / "portability_common.py"
    pattern = "not isinstance(value, int) or isinstance(value, bool)"
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    backup = tmp_path / "portability_common.py.bak"
    applied = _apply_mutation(target, pattern, "not isinstance(value, int)", backup)
    if not applied:
        return "DID-NOT-APPLY: replace had no effect"

    proc = _run_suite()
    result = _classify(proc)
    _restore(target, backup)
    return result


def mutant_m2_diff_attr_guard(tmp_path: Path) -> str:
    """M2: swap 'unset' for 'set' in the diff-attribute guard."""
    target = SCRIPTS / "portability_baseline.py"
    pattern = 'if attr != "unset":'
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    backup = tmp_path / "portability_baseline.py.bak"
    applied = _apply_mutation(
        target, pattern, 'if attr != "set":', backup
    )
    if not applied:
        return "DID-NOT-APPLY: replace had no effect"

    proc = _run_suite()
    result = _classify(proc)
    _restore(target, backup)
    return result


def mutant_m2b_diff_attr_none_guard(tmp_path: Path) -> str:
    """M2b: flip None check to fail-open (contradicts fail-closed spec)."""
    target = SCRIPTS / "portability_baseline.py"
    pattern = "    if attr is None:\n"
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    backup = tmp_path / "portability_baseline_none.py.bak"
    applied = _apply_mutation(target, pattern, "    if attr is not None:\n", backup)
    if not applied:
        return "DID-NOT-APPLY: replace had no effect"

    proc = _run_suite()
    result = _classify(proc)
    _restore(target, backup)
    return result


def mutant_m3_scan_all_roots(tmp_path: Path) -> str:
    """M3: drop the SCAN_ROOTS loop in scan_all (empty all result dicts)."""
    target = SCRIPTS / "check_skill_md_exec_portability.py"
    pattern = "    for parts in SCAN_ROOTS:"
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    backup = tmp_path / "check_skill_md_exec.py.bak"
    applied = _apply_mutation(target, pattern, "    for parts in []:", backup)
    if not applied:
        return "DID-NOT-APPLY: replace had no effect"

    proc = _run_suite()
    result = _classify(proc)
    _restore(target, backup)
    return result


def mutant_m4_inverted_control_benign(tmp_path: Path) -> str:
    """Inverted control: a benign change must SURVIVE (harness sanity check).

    Changes an unrelated comment in portability_common.py. The suite must
    pass (rc == 0) after this mutation. If it does not, the harness or tests
    are broken, not the production code.
    """
    target = SCRIPTS / "portability_common.py"
    pattern = '"""Read and validate a portability ratchet baseline."""'
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    backup = tmp_path / "portability_common_ctrl.py.bak"
    applied = _apply_mutation(
        target,
        pattern,
        '"""Read and validate a portability ratchet baseline. (benign)"""',
        backup,
    )
    if not applied:
        return "DID-NOT-APPLY: replace had no effect"

    proc = _run_suite()
    result = _classify(proc)
    _restore(target, backup)

    # Inverted control: must SURVIVE.
    if result != "SURVIVED":
        return f"INVERTED-CONTROL-FAILED: expected SURVIVED, got {result}"
    return "SURVIVED"


def main() -> int:
    import tempfile

    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        results["M1-bool-check"] = mutant_m1_bool_check(tmp_path)
        results["M2-diff-attr-guard"] = mutant_m2_diff_attr_guard(tmp_path)
        results["M2b-diff-attr-none-guard"] = mutant_m2b_diff_attr_none_guard(tmp_path)
        results["M3-scan-all-roots"] = mutant_m3_scan_all_roots(tmp_path)
        results["M4-inverted-ctrl"] = mutant_m4_inverted_control_benign(tmp_path)

    print("\n=== Mutation Results ===")
    all_ok = True
    for name, result in results.items():
        expected = "SURVIVED" if "inverted" in name.lower() else "DEAD"
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {result}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nFAILURE: one or more mutants survived or inverted control failed")
        return 1
    print("\nAll mutants killed; inverted control survived.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
