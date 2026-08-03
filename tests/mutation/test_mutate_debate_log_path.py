"""Mutation harness for the debate-log canonical path fix (Issue #4250).

The fix changed git_hook_policy.py to search .agents/critique/ instead of
.agents/analysis/ for debate logs in check_adr_review_policy().

Three mutants and one inverted control:

  M1 (positive): revert the directory name "critique" back to "analysis".
      Expected: DEAD (tests detect the regression).

  M2 (positive): change the error message path from .agents/critique to
      .agents/wrong-dir.
      Expected: DEAD (tests detect the wrong message).

  M3 (positive): comment out the missing-debate-log early return so a missing
      log no longer fails.
      Expected: DEAD (tests detect missing gate).

  IC (inverted control): no-op mutation that changes a comment but not logic.
      Expected: SURVIVED (rc == 0). Proves the harness can tell green from red.

All test nodes assert:
  - returncode != 4 (no "file or directory not found" from pytest)
  - "no tests ran" not in stdout (suite collected at least one test)

Counting occurs before each mutation; DID-NOT-APPLY is reported if the literal
is absent (count == 0) and is an error exit.

Isolation (Issue #4457): mutations are applied inside a temporary git worktree
so the tracked source file in the caller's working tree is never modified.
The worktree is created once per test session and removed on teardown; abrupt
termination leaves only an orphan worktree under ~/src/scratch/, not a dirty
tracked file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Path relative to repo root; used to locate the file inside the mutation worktree.
TARGET_REL = Path("scripts") / "validation" / "git_hook_policy.py"
# Keep the mutation run narrow so it stays below pytest-timeout when the full suite is running.
TESTS = [
    "tests/test_lefthook_integration.py::test_adr_review_policy_missing_critique_dir_fails"
]

_OUTCOME_DEAD = "DEAD"
_OUTCOME_SURVIVED = "SURVIVED"
_OUTCOME_DID_NOT_APPLY = "DID-NOT-APPLY"
# Scratch directory for mutation worktrees (never /tmp; survives SIGKILL for recovery).
_SCRATCH = Path(os.path.expanduser("~/src/scratch"))


# ---------------------------------------------------------------------------
# Session-scoped worktree fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mutation_worktree() -> Generator[tuple[Path, Path], None, None]:
    """Create a temporary git worktree for the session; remove it on teardown.

    Yields (wt_root, wt_target) where wt_root is the worktree root and
    wt_target is the path to git_hook_policy.py inside the worktree.

    The worktree is detached from any branch so mutations to wt_target never
    appear in the caller's working tree or index.
    """

    wt_path = _SCRATCH / f"mut-debate-{os.getpid()}"

    subprocess.run(
        ["git", "worktree", "add", "--detach", str(wt_path), "HEAD"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
    )

    # Bootstrap the venv inside the worktree so `uv run` resolves modules
    # from wt_path/scripts/, not the caller's scripts/.
    subprocess.run(
        ["uv", "run", "--frozen", "python", "-c", "import scripts.validation.git_hook_policy"],
        cwd=str(wt_path),
        check=True,
        capture_output=True,
    )

    wt_target = wt_path / TARGET_REL

    def _gen() -> Generator[tuple[Path, Path], None, None]:
        try:
            yield wt_path, wt_target
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt_path)],
                cwd=str(REPO_ROOT),
                check=False,
                capture_output=True,
            )

    yield from _gen()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_tests(wt_root: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q", *TESTS]
    # Use the worktree's own Python so imports resolve from wt_root/scripts/.
    wt_python = wt_root / ".venv" / "bin" / "python"
    if wt_python.exists():
        cmd[0] = str(wt_python)
    return subprocess.run(
        cmd,
        cwd=str(wt_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _assert_suite_ran(result: subprocess.CompletedProcess[str], label: str) -> None:
    assert result.returncode != 4, (
        f"{label}: pytest exited 4 (file or directory not found). "
        "Suite was never collected.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "no tests ran" not in result.stdout.lower(), (
        f"{label}: no tests were collected.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _apply_positive_mutant(
    wt_target: Path,
    original: bytes,
    original_fragment: bytes,
    mutant_fragment: bytes,
    label: str,
    wt_root: Path,
) -> str:
    """Apply a mutant to the worktree copy and assert the suite detects it (DEAD)."""
    count = original.count(original_fragment)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} ({label}): literal not found in target. "
            "The file was changed; update this harness."
        )
    if count > 1:
        raise AssertionError(
            f"PATTERN-AMBIGUOUS ({label}): expected 1 occurrence, found {count}."
        )

    mutated = original.replace(original_fragment, mutant_fragment, 1)
    assert mutated != original, f"Mutation {label} produced a byte-identical file"

    # Purge cached bytecode before writing the mutant.
    _purge_pycache(wt_target.parent)

    wt_target.write_bytes(mutated)
    time.sleep(1.1)  # defeat 1-second bytecode mtime granularity

    result = _run_tests(wt_root)
    _assert_suite_ran(result, label)

    # Restore worktree copy regardless of outcome so later mutants start clean.
    _purge_pycache(wt_target.parent)
    wt_target.write_bytes(original)
    time.sleep(1.1)

    assert result.returncode != 0, (
        f"MUTANT SURVIVED ({label}): suite passed after mutation. "
        "Tests do not detect the regression.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    restored = wt_target.read_bytes()
    assert restored == original, f"Worktree file not restored byte-identically after {label}"

    return _OUTCOME_DEAD


def _purge_pycache(directory: Path) -> None:
    """Remove __pycache__ dirs under directory to defeat stale bytecode."""
    for cache in directory.rglob("__pycache__"):
        if cache.is_dir():
            import shutil  # noqa: PLC0415

            shutil.rmtree(cache, ignore_errors=True)


# ---------------------------------------------------------------------------
# M1: revert directory name from "critique" back to "analysis"
# ---------------------------------------------------------------------------

_M1_ORIGINAL = b'    critique_dir = repo_root / ".agents" / "critique"\n'
_M1_MUTANT = b'    critique_dir = repo_root / ".agents" / "analysis"  # M1 mutant\n'


def test_m1_directory_name_reverted_is_detected(mutation_worktree: tuple[Path, Path]) -> None:
    wt_root, wt_target = mutation_worktree
    original = wt_target.read_bytes()
    outcome = _apply_positive_mutant(
        wt_target, original, _M1_ORIGINAL, _M1_MUTANT, "M1-dir-name", wt_root
    )
    assert outcome == _OUTCOME_DEAD
    # Inverted verification: suite still passes after restore.
    result = _run_tests(wt_root)
    _assert_suite_ran(result, "M1-restore-check")
    assert result.returncode == 0, (
        "Tests failed after restoring original (M1).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# M2: change the error message to reference a wrong directory
# ---------------------------------------------------------------------------

_M2_ORIGINAL = (
    b'        print("ERROR: ADR changes require a debate log in .agents/critique",'
    b" file=sys.stderr)\n"
)
_M2_MUTANT = (
    b'        print("ERROR: ADR changes require a debate log in .agents/wrong-dir",'
    b"  # M2 mutant\n"
    b'               file=sys.stderr)\n'
)


def test_m2_error_message_path_changed_is_detected(mutation_worktree: tuple[Path, Path]) -> None:
    wt_root, wt_target = mutation_worktree
    original = wt_target.read_bytes()
    outcome = _apply_positive_mutant(
        wt_target, original, _M2_ORIGINAL, _M2_MUTANT, "M2-error-msg", wt_root
    )
    assert outcome == _OUTCOME_DEAD
    result = _run_tests(wt_root)
    _assert_suite_ran(result, "M2-restore-check")
    assert result.returncode == 0, (
        "Tests failed after restoring original (M2).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# M3: remove the missing-debate-log early return
# ---------------------------------------------------------------------------

_M3_ORIGINAL = (
    b"    if not debate_logs:\n"
    b'        print("ERROR: ADR changes require a debate log in .agents/critique",'
    b" file=sys.stderr)\n"
    b"        return 1\n"
)
_M3_MUTANT = (
    b"    if False:  # M3 mutant: gate removed\n"
    b'        print("ERROR: ADR changes require a debate log in .agents/critique",'
    b" file=sys.stderr)\n"
    b"        return 1\n"
)


def test_m3_missing_debate_log_gate_removed_is_detected(
    mutation_worktree: tuple[Path, Path],
) -> None:
    wt_root, wt_target = mutation_worktree
    original = wt_target.read_bytes()
    outcome = _apply_positive_mutant(
        wt_target, original, _M3_ORIGINAL, _M3_MUTANT, "M3-gate-removed", wt_root
    )
    assert outcome == _OUTCOME_DEAD
    result = _run_tests(wt_root)
    _assert_suite_ran(result, "M3-restore-check")
    assert result.returncode == 0, (
        "Tests failed after restoring original (M3).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# IC: inverted control - change a comment only; suite MUST survive (rc == 0)
# ---------------------------------------------------------------------------

_IC_ORIGINAL = (
    b"    # Canonical debate-log directory per:\n"
    b"    #   .claude/skills/adr-review/references/artifacts.md line 3:\n"
    b'    #     "Save debate artifacts to `.agents/critique/`."\n'
    b"    #   .claude/skills/adr-review/references/artifacts.md line 7:\n"
    b'    #     "Save to: `.agents/critique/ADR-NNN-debate-log.md`"\n'
    b"    # Issue #4250: the hook previously searched .agents/analysis/ but the\n"
    b"    # skill writes to .agents/critique/.\n"
)
_IC_MUTANT = (
    b"    # Canonical debate-log directory per:\n"
    b"    #   .claude/skills/adr-review/references/artifacts.md line 3:\n"
    b'    #     "Save debate artifacts to `.agents/critique/`."\n'
    b"    #   .claude/skills/adr-review/references/artifacts.md line 7:\n"
    b'    #     "Save to: `.agents/critique/ADR-NNN-debate-log.md`"\n'
    b"    # Issue #4250: the hook previously searched .agents/analysis/ but the\n"
    b"    # skill writes to .agents/critique/.  # IC mutant\n"
)


def test_ic_comment_only_change_survives(mutation_worktree: tuple[Path, Path]) -> None:
    """Inverted control: a comment-only mutation must NOT be detected (rc == 0)."""
    wt_root, wt_target = mutation_worktree

    original = wt_target.read_bytes()
    count = original.count(_IC_ORIGINAL)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} (IC): comment literal not found. "
            "Update this harness to match the current comment."
        )
    if count > 1:
        raise AssertionError(f"PATTERN-AMBIGUOUS (IC): {count} occurrences found.")

    mutated = original.replace(_IC_ORIGINAL, _IC_MUTANT, 1)
    assert mutated != original, "IC mutation produced a byte-identical file"

    _purge_pycache(wt_target.parent)
    wt_target.write_bytes(mutated)
    time.sleep(1.1)

    result = _run_tests(wt_root)
    _assert_suite_ran(result, "IC")

    _purge_pycache(wt_target.parent)
    wt_target.write_bytes(original)
    time.sleep(1.1)

    assert result.returncode == 0, (
        "INVERTED CONTROL FAILED (IC): suite rejected a comment-only change. "
        "The harness is over-sensitive or a test matches comments.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    restored = wt_target.read_bytes()
    assert restored == original, "Worktree file not restored byte-identically after IC"
