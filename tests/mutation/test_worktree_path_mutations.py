#!/usr/bin/env python3
"""Mutation harness for issues #4160, #4161, #4194.

Reports three outcomes per mutation:
  DEAD         - test suite caught the mutation (expected)
  SURVIVED     - test suite passed despite the mutation (bug in tests)
  DID-NOT-APPLY - the target literal was absent; file was not mutated

A DID-NOT-APPLY exits nonzero and aborts the run. A SURVIVED also exits
nonzero. The harness additionally uses cmp -s to detect byte-identical files
and fails if a "mutated" file is unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO_ROOT)


def _count_occurrences(path: Path, needle: str) -> int:
    return path.read_text(encoding="utf-8").count(needle)


def _apply_mutation(path: Path, original: str, mutant: str, backup: Path) -> bool:
    """Replace ``original`` with ``mutant`` in ``path``.

    Writes a backup, applies the replacement, then uses ``cmp -s`` to assert
    the file actually changed (byte-identical file means the mutation did not
    apply). Returns True on success.
    """
    text = path.read_text(encoding="utf-8")
    if original not in text:
        return False  # DID-NOT-APPLY
    shutil.copy2(path, backup)
    mutated = text.replace(original, mutant, 1)
    path.write_text(mutated, encoding="utf-8")
    # cmp -s: exit 0 means files are identical (mutation did not change bytes)
    result = subprocess.run(["cmp", "-s", str(path), str(backup)], capture_output=True)
    if result.returncode == 0:
        shutil.copy2(backup, path)
        return False  # byte-identical: DID-NOT-APPLY
    return True


def _restore(path: Path, backup: Path) -> None:
    shutil.copy2(backup, path)
    restored = subprocess.run(["cmp", "-s", str(path), str(backup)], capture_output=True)
    assert restored.returncode == 0, (
        f"FATAL: restore of {path} is not byte-identical to backup"
    )


def _run_tests(test_paths: list[str]) -> bool:
    """Return True if the test suite passes."""
    result = _run(
        [
            sys.executable, "-m", "pytest",
            *test_paths,
            "-q", "--tb=no", "-x",
        ]
    )
    return result.returncode == 0


def _mutation(
    label: str,
    target_path: Path,
    original: str,
    mutant: str,
    test_paths: list[str],
) -> str:
    """Apply one mutation and return 'DEAD', 'SURVIVED', or 'DID-NOT-APPLY'."""
    count = _count_occurrences(target_path, original)
    if count == 0:
        print(f"  [{label}] DID-NOT-APPLY: '{original}' not found in {target_path.name}")
        return "DID-NOT-APPLY"
    if count > 1:
        print(
            f"  [{label}] WARNING: '{original}' appears {count} times; "
            "mutating first occurrence only"
        )

    backup = target_path.with_suffix(".bak")
    applied = _apply_mutation(target_path, original, mutant, backup)
    if not applied:
        print(f"  [{label}] DID-NOT-APPLY: file unchanged after substitution")
        if backup.exists():
            backup.unlink()
        return "DID-NOT-APPLY"

    try:
        suite_passed = _run_tests(test_paths)
    finally:
        _restore(target_path, backup)
        backup.unlink()

    if suite_passed:
        print(f"  [{label}] SURVIVED: test suite passed with mutant applied")
        return "SURVIVED"

    print(f"  [{label}] DEAD: test suite caught the mutation")
    return "DEAD"


def main() -> int:
    mutations: list[tuple[str, Path, str, str, list[str]]] = [
        # Issue #4160: relative vs absolute path parts in skip filter
        (
            "#4160 relative-parts",
            REPO_ROOT / "tests/ci/test_validation_scripts_are_reachable.py",
            "p.relative_to(_REPO_ROOT).parts",
            "p.parts",
            [
                "tests/ci/test_worktree_path_filter.py",
                "tests/ci/test_validation_scripts_are_reachable.py",
            ],
        ),
        # Issue #4194: _session_log_for_current_branch in check_adr_review_policy
        (
            "#4194 adr-uses-branch-log",
            REPO_ROOT / "scripts/validation/git_hook_policy.py",
            "_session_log_for_current_branch(repo_root / \".agents\" / \"sessions\", repo_root)\n"
            "    if session_log is None or not _session_has_adr_review(session_log):",
            "_today_session_log(repo_root / \".agents\" / \"sessions\")\n"
            "    if session_log is None or not _session_has_adr_review(session_log):",
            [
                "tests/validation/test_session_log_branch_aware.py",
                "tests/validation/test_git_hook_policy_causal_restore.py",
            ],
        ),
        # Issue #4194: _session_log_for_current_branch in check_retrospective_evidence
        (
            "#4194 retro-uses-branch-log",
            REPO_ROOT / "scripts/validation/git_hook_policy.py",
            "_session_log_for_current_branch(repo_root / \".agents\" / \"sessions\", repo_root)\n"
            "    if paths and _is_trivial_retrospective_session(session_log, paths):",
            "_today_session_log(repo_root / \".agents\" / \"sessions\")\n"
            "    if paths and _is_trivial_retrospective_session(session_log, paths):",
            [
                "tests/validation/test_session_log_branch_aware.py",
                "tests/validation/test_git_hook_policy_causal_restore.py",
            ],
        ),
        # Issue #4194: _session_log_for_current_branch helper branch-first selection
        (
            "#4194 helper-branch-first",
            REPO_ROOT / "scripts/validation/git_hook_policy.py",
            "        if log is not None:\n            return log\n    return _today_session_log",
            "        if log is not None:\n            pass  # mutant: skip branch return\n"
            "    return _today_session_log",
            [
                "tests/validation/test_session_log_branch_aware.py",
            ],
        ),
        # Issue #4161: branch-first selection in _find_current_session_log
        (
            "#4161 branch-match",
            REPO_ROOT
            / ".claude/skills/session-end/scripts/complete_session_log.py",
            "if log_branch == branch:\n                return full",
            "if log_branch == branch:\n                pass  # mutant: skip branch return",
            [
                "tests/skills/test_session_scripts.py",
            ],
        ),
        # Issue #4161: _get_current_branch empty-string guard
        (
            "#4161 empty-branch-guard",
            REPO_ROOT
            / ".claude/skills/session-end/scripts/complete_session_log.py",
            "return branch or None",
            "return branch",
            [
                "tests/skills/test_session_scripts.py",
            ],
        ),
    ]

    results: dict[str, list[str]] = {"DEAD": [], "SURVIVED": [], "DID-NOT-APPLY": []}

    print("=" * 60)
    print("Mutation harness: worktree path resolution fixes")
    print("=" * 60)

    for label, path, original, mutant, tests in mutations:
        print(f"\nMutation: {label}")
        outcome = _mutation(label, path, original, mutant, tests)
        results[outcome].append(label)

    print("\n" + "=" * 60)
    print("Results:")
    for outcome, labels in results.items():
        for label in labels:
            print(f"  {outcome:16s} {label}")

    dead = len(results["DEAD"])
    survived = len(results["SURVIVED"])
    did_not_apply = len(results["DID-NOT-APPLY"])

    print(f"\nSummary: {dead} DEAD, {survived} SURVIVED, {did_not_apply} DID-NOT-APPLY")

    if survived:
        print("FAIL: surviving mutants indicate missing test coverage", file=sys.stderr)
        return 1
    if did_not_apply:
        print(
            "FAIL: DID-NOT-APPLY mutations indicate the target literal has changed; "
            "update the harness",
            file=sys.stderr,
        )
        return 1

    print("PASS: all mutants killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
