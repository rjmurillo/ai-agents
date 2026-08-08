"""Mutation harness for the debate-log canonical path fix (Issue #4250).

Isolation model (Issues #4346, #4457)
--------------------------------------
Every mutation runs inside a temporary git worktree created from HEAD. The
active worktree's tracked files are NEVER written. If the test process is
killed at any point, the active worktree stays clean and `git status --short`
remains empty. The scratch worktree is removed in a `finally` block; if that
also fails, git expunges it when the caller runs `git worktree prune`.

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

Counting occurs before each mutation; DID-NOT-APPLY is raised if the literal
is absent (count == 0).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET_REL = Path("scripts") / "validation" / "git_hook_policy.py"
# Test paths are relative so the subprocess can resolve them from its own cwd.
_TESTS = ["tests/test_lefthook_integration.py"]

_OUTCOME_DEAD = "DEAD"
_OUTCOME_SURVIVED = "SURVIVED"
_OUTCOME_DID_NOT_APPLY = "DID-NOT-APPLY"


def _add_scratch_worktree(base: Path) -> Path:
    """Create a scratch worktree from HEAD. Returns the worktree path."""
    wt_path = base / "mutation_wt"
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(wt_path), "HEAD"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"git worktree add failed:\n{result.stderr}"
    return wt_path


def _remove_scratch_worktree(wt_path: Path) -> None:
    """Remove the scratch worktree. Tolerates errors (git prune will clean up)."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(wt_path)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


def _run_tests_in(wt_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the lefthook integration test suite from a scratch worktree."""
    pycache = wt_path / "scripts" / "validation" / "__pycache__"
    if pycache.exists():
        import shutil

        shutil.rmtree(pycache)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=short",
        "-q",
        "--import-mode=importlib",
        *_TESTS,
    ]
    return subprocess.run(
        cmd,
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **__import__("os").environ,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


def _assert_suite_ran(result: subprocess.CompletedProcess[str], label: str) -> None:
    assert result.returncode != 4, (
        f"{label}: pytest exited 4 (file or directory not found). "
        "Suite was never collected.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "no tests ran" not in result.stdout.lower(), (
        f"{label}: no tests were collected.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _apply_positive_mutant(
    wt_path: Path,
    original: bytes,
    original_fragment: bytes,
    mutant_fragment: bytes,
    label: str,
) -> str:
    """Apply mutant in scratch worktree and assert suite detects it (DEAD)."""
    count = original.count(original_fragment)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} ({label}): literal not found in target. "
            "The file was changed; update this harness."
        )
    if count > 1:
        raise AssertionError(f"PATTERN-AMBIGUOUS ({label}): expected 1 occurrence, found {count}.")

    mutated = original.replace(original_fragment, mutant_fragment, 1)
    assert mutated != original, f"Mutation {label} produced a byte-identical file"

    wt_target = wt_path / _TARGET_REL
    wt_target.write_bytes(mutated)

    result = _run_tests_in(wt_path)

    # Restore original bytes before asserting so the restore check below
    # always runs against the unmodified file.
    wt_target.write_bytes(original)

    _assert_suite_ran(result, label)

    assert result.returncode != 0, (
        f"MUTANT SURVIVED ({label}): suite passed after mutation. "
        "Tests do not detect the regression.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return _OUTCOME_DEAD


@pytest.fixture()
def scratch_worktree(tmp_path: Path):
    """Provide a scratch git worktree; remove it after the test."""
    wt = _add_scratch_worktree(tmp_path)
    try:
        yield wt
    finally:
        _remove_scratch_worktree(wt)


def _active_target_unmodified() -> bool:
    """Return True when the mutation target file is unmodified in the active worktree.

    Checks only the target file, not the entire worktree. Other in-progress
    changes (baseline updates, session logs) must not produce false failures.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", str(_TARGET_REL)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    # Also check the working-tree against the index (unstaged changes).
    result2 = subprocess.run(
        ["git", "diff", "--name-only", "--", str(_TARGET_REL)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    return result.stdout.strip() == "" and result2.stdout.strip() == ""


# ---------------------------------------------------------------------------
# M1: revert directory name from "critique" back to "analysis"
# ---------------------------------------------------------------------------

_M1_ORIGINAL = b'    critique_dir = repo_root / ".agents" / "critique"\n'
_M1_MUTANT = b'    critique_dir = repo_root / ".agents" / "analysis"  # M1 mutant\n'


def test_m1_directory_name_reverted_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M1_ORIGINAL, _M1_MUTANT, "M1-dir-name"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M1"
    # Restore check: suite passes against the unmodified tree.
    result = _run_tests_in(scratch_worktree)
    _assert_suite_ran(result, "M1-restore-check")
    assert result.returncode == 0, (
        "Tests failed against unmodified worktree after M1.\n"
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
    b"               file=sys.stderr)\n"
)


def test_m2_error_message_path_changed_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M2_ORIGINAL, _M2_MUTANT, "M2-error-msg"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M2"
    result = _run_tests_in(scratch_worktree)
    _assert_suite_ran(result, "M2-restore-check")
    assert result.returncode == 0, (
        "Tests failed against unmodified worktree after M2.\n"
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


def test_m3_missing_debate_log_gate_removed_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M3_ORIGINAL, _M3_MUTANT, "M3-gate-removed"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M3"
    result = _run_tests_in(scratch_worktree)
    _assert_suite_ran(result, "M3-restore-check")
    assert result.returncode == 0, (
        "Tests failed against unmodified worktree after M3.\n"
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


def test_ic_comment_only_change_survives(scratch_worktree: Path) -> None:
    """Inverted control: a comment-only mutation must NOT be detected (rc == 0)."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()

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

    wt_target = scratch_worktree / _TARGET_REL
    wt_target.write_bytes(mutated)

    result = _run_tests_in(scratch_worktree)
    _assert_suite_ran(result, "IC")

    assert result.returncode == 0, (
        "INVERTED CONTROL FAILED (IC): suite rejected a comment-only change. "
        "The harness is over-sensitive or a test matches comments.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after IC"


# ---------------------------------------------------------------------------
# Isolation guarantee test (issue #4346)
# ---------------------------------------------------------------------------


def test_scratch_worktree_created_and_removed(tmp_path: Path) -> None:
    """The scratch worktree fixture creates an isolated tree and removes it.

    Verifies that:
    - The scratch worktree exists and contains the target file.
    - A mutation written to the scratch worktree does NOT appear in the active tree.
    - After the fixture tears down, the scratch worktree directory is gone.
    """
    wt = _add_scratch_worktree(tmp_path)
    try:
        wt_target = wt / _TARGET_REL
        assert wt_target.exists(), "Scratch worktree missing the target file"

        original_active = (REPO_ROOT / _TARGET_REL).read_bytes()
        sentinel = b"# ISOLATION-SENTINEL\n"
        wt_target.write_bytes(original_active + sentinel)

        active_bytes = (REPO_ROOT / _TARGET_REL).read_bytes()
        assert sentinel not in active_bytes, (
            "Writing to scratch worktree leaked into the active worktree"
        )
    finally:
        _remove_scratch_worktree(wt)

    assert not (tmp_path / "mutation_wt").exists(), (
        "Scratch worktree directory still exists after removal"
    )
