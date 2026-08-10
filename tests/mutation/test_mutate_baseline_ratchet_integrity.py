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
  - applied in an isolated git worktree, suite run, result classified
  - restored and verified byte-identically inside the scratch worktree

One inverted control asserts rc == 0 (suite SURVIVES a benign mutation).
All test files are referenced by filesystem path, never dotted module name.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_REL = Path("scripts") / "validation"
TEST_PATH = Path("tests") / "validation" / "test_baseline_ratchet_integrity.py"
TARGETS = (
    SCRIPTS_REL / "portability_common.py",
    SCRIPTS_REL / "portability_baseline.py",
    SCRIPTS_REL / "check_skill_md_exec_portability.py",
)


def _run_suite(repo_root: Path, *extra_paths: str) -> subprocess.CompletedProcess[str]:
    """Run pytest on the integrity test file plus optional extra paths."""
    for pycache in (repo_root / SCRIPTS_REL).rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache)
    paths = [str(TEST_PATH), *extra_paths]
    return subprocess.run(
        ["uv", "run", "--frozen", "python", "-m", "pytest", *paths, "-q", "--tb=short"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(repo_root),
        env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
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


def _apply_mutation(path: Path, old: str, new: str) -> bytes | None:
    """Apply a mutation and return original bytes, or None when absent."""
    original = path.read_bytes()
    text = path.read_text()
    if old not in text:
        return None
    path.write_text(text.replace(old, new, 1))
    assert path.read_bytes() != original, "mutation produced a byte-identical file"
    return original


def _restore(path: Path, original: bytes) -> None:
    path.write_bytes(original)
    assert path.read_bytes() == original, "restore check failed: bytes differ"


def mutant_m1_bool_check(repo_root: Path) -> str:
    """M1: weaken bool rejection so bool values slip through as integers."""
    target = repo_root / SCRIPTS_REL / "portability_common.py"
    pattern = "not isinstance(value, int) or isinstance(value, bool)"
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    original = _apply_mutation(target, pattern, "not isinstance(value, int)")
    if original is None:
        return "DID-NOT-APPLY: replace had no effect"

    try:
        proc = _run_suite(repo_root)
        result = _classify(proc)
    finally:
        _restore(target, original)
    return result


def mutant_m2_diff_attr_guard(repo_root: Path) -> str:
    """M2: swap 'unset' for 'set' in the diff-attribute guard."""
    target = repo_root / SCRIPTS_REL / "portability_baseline.py"
    pattern = 'if attr != "unset":'
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    original = _apply_mutation(target, pattern, 'if attr != "set":')
    if original is None:
        return "DID-NOT-APPLY: replace had no effect"

    try:
        proc = _run_suite(repo_root)
        result = _classify(proc)
    finally:
        _restore(target, original)
    return result


def mutant_m2b_diff_attr_none_guard(repo_root: Path) -> str:
    """M2b: flip None check to fail-open (contradicts fail-closed spec)."""
    target = repo_root / SCRIPTS_REL / "portability_baseline.py"
    pattern = "    if attr is None:\n"
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    original = _apply_mutation(target, pattern, "    if attr is not None:\n")
    if original is None:
        return "DID-NOT-APPLY: replace had no effect"

    try:
        proc = _run_suite(repo_root)
        result = _classify(proc)
    finally:
        _restore(target, original)
    return result


def mutant_m3_scan_all_roots(repo_root: Path) -> str:
    """M3: drop the SCAN_ROOTS loop in scan_all (empty all result dicts)."""
    target = repo_root / SCRIPTS_REL / "check_skill_md_exec_portability.py"
    # Use context unique to scan_all because other functions also scan SCAN_ROOTS.
    pattern = (
        "    marker_counts: dict[str, int] = {}\n"
        "    files_by_root: dict[str, int] = {}\n"
        "    for parts in SCAN_ROOTS:"
    )
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    original = _apply_mutation(
        target,
        pattern,
        "    marker_counts: dict[str, int] = {}\n"
        "    files_by_root: dict[str, int] = {}\n"
        "    for parts in []:",
    )
    if original is None:
        return "DID-NOT-APPLY: replace had no effect"

    try:
        proc = _run_suite(repo_root)
        result = _classify(proc)
    finally:
        _restore(target, original)
    return result


def mutant_m4_inverted_control_benign(repo_root: Path) -> str:
    """Inverted control: a benign change must SURVIVE (harness sanity check).

    Changes an unrelated comment in portability_common.py. The suite must
    pass (rc == 0) after this mutation. If it does not, the harness or tests
    are broken, not the production code.
    """
    target = repo_root / SCRIPTS_REL / "portability_common.py"
    pattern = '"""Read and validate a portability ratchet baseline."""'
    count = _count_occurrences(target, pattern)
    if count == 0:
        return "DID-NOT-APPLY: pattern absent"
    if count > 1:
        return f"DID-NOT-APPLY: ambiguous, {count} occurrences"

    original = _apply_mutation(
        target,
        pattern,
        '"""Read and validate a portability ratchet baseline. (benign)"""',
    )
    if original is None:
        return "DID-NOT-APPLY: replace had no effect"

    try:
        proc = _run_suite(repo_root)
        result = _classify(proc)
    finally:
        _restore(target, original)

    # Inverted control: must SURVIVE.
    if result != "SURVIVED":
        return f"INVERTED-CONTROL-FAILED: expected SURVIVED, got {result}"
    return "SURVIVED"


def main() -> int:
    results: dict[str, str] = {}
    with isolated_mutation_worktree(REPO_ROOT, TARGETS) as workspace:
        results["M1-bool-check"] = mutant_m1_bool_check(workspace.root)
        results["M2-diff-attr-guard"] = mutant_m2_diff_attr_guard(workspace.root)
        results["M2b-diff-attr-none-guard"] = mutant_m2b_diff_attr_none_guard(
            workspace.root
        )
        results["M3-scan-all-roots"] = mutant_m3_scan_all_roots(workspace.root)
        results["M4-inverted-ctrl"] = mutant_m4_inverted_control_benign(
            workspace.root
        )

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


# pytest-discoverable wrappers (issue #4494: file had no test_* functions,
# so pytest collected 0 items and reported exit 5 as success).


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    with isolated_mutation_worktree(REPO_ROOT, TARGETS) as workspace:
        yield workspace.root


def test_m1_bool_check_is_dead(mutation_repo: Path) -> None:
    """M1 must be killed by the suite."""
    assert mutant_m1_bool_check(mutation_repo) == "DEAD"


def test_m2_diff_attr_guard_is_dead(mutation_repo: Path) -> None:
    """M2 must be killed by the suite."""
    assert mutant_m2_diff_attr_guard(mutation_repo) == "DEAD"


def test_m2b_diff_attr_none_guard_is_dead(mutation_repo: Path) -> None:
    """M2b must be killed by the suite."""
    assert mutant_m2b_diff_attr_none_guard(mutation_repo) == "DEAD"


def test_m3_scan_all_roots_is_dead(mutation_repo: Path) -> None:
    """M3 must be killed by the suite."""
    assert mutant_m3_scan_all_roots(mutation_repo) == "DEAD"


def test_m4_inverted_control_survives(mutation_repo: Path) -> None:
    """The cosmetic control must survive (exit 0); any kill here means false kills."""
    assert mutant_m4_inverted_control_benign(mutation_repo) == "SURVIVED"
