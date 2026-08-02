# taste-lint: ignore file-size -- mutation harness; tests and policy are tightly paired.
"""Mutation harness for push policy fixes (issues #4086, #4236, #4283).

Each mutation replaces one load-bearing expression in git_hook_policy.py with a
broken equivalent, runs the targeted regression tests, and asserts they catch
the breakage. Restoration always uses `git checkout`, never string replacement,
so mutations cannot leave the file in a corrupted state.

Requirements from TESTING-RIGOR.md:
- Target test FILES BY FILESYSTEM PATH, never a dotted module name.
- Assert "no tests ran" is absent and returncode != 4.
- cd to worktree root first.
- Count occurrences and exit non-zero on DID-NOT-APPLY.
- Include one inverted control that MUST SURVIVE.
- Restore baseline green at the end.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

_REPO = Path(__file__).parent.parent
_POLICY = _REPO / "scripts" / "validation" / "git_hook_policy.py"
_TESTS = _REPO / "tests" / "test_lefthook_integration.py"
_BACKUP = _REPO / "scripts" / "validation" / "git_hook_policy.py.mutation_backup"


def _run_targeted(test_filter: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_TESTS),
            "-k",
            test_filter,
            "-q",
            "--tb=no",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=_REPO,
    )


@contextmanager
def _mutated(old: str, new: str) -> Generator[int]:
    """Context manager that applies a mutation, yields occurrence count, restores.

    Restoration copies the backup rather than reversing the string substitution
    so partial or nested mutations cannot corrupt the file.
    """
    content = _POLICY.read_text(encoding="utf-8")
    count = content.count(old)
    _BACKUP.write_text(content, encoding="utf-8")
    try:
        if count > 0:
            _POLICY.write_text(content.replace(old, new, 1), encoding="utf-8")
        yield count
    finally:
        shutil.copy2(_BACKUP, _POLICY)
        _BACKUP.unlink(missing_ok=True)


def _assert_ran(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode != 4, f"pytest exit 4 (no files): {result.stdout}"
    assert "no tests ran" not in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# Inverted control: baseline must always be green (MUST SURVIVE).
# ---------------------------------------------------------------------------


def test_baseline_passes_without_mutation() -> None:
    """Sanity check: targeted tests pass on unmodified code."""
    result = _run_targeted(
        "push_files_warning or history_integrity_shallow_message"
    )
    _assert_ran(result)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# #4086: shallow message must name the remedy.
# ---------------------------------------------------------------------------


def test_mutation_removing_unshallow_remedy_is_caught() -> None:
    """Removing 'git fetch --unshallow origin' from the error text must cause
    test_history_integrity_shallow_message_names_remedy to fail."""
    old = '"\\n  Fix: git fetch --unshallow origin",'
    new = '"\\n  Fix: (remedy removed by mutation)",'
    with _mutated(old, new) as count:
        assert count > 0, f"DID-NOT-APPLY: {old!r} not found in {_POLICY}"
        result = _run_targeted("history_integrity_shallow_message_names_remedy")
        _assert_ran(result)
        assert result.returncode != 0, (
            "Mutation survived: removing unshallow remedy was not caught"
        )


def test_mutation_removing_pin_sha_read_is_caught() -> None:
    """Replacing the pin-SHA read with an empty constant must cause
    test_history_integrity_shallow_message_names_pin_sha to fail."""
    old = "pin_sha = first_line[0].strip() if first_line else \"\""
    new = 'pin_sha = ""  # mutation: pin-sha read removed'
    with _mutated(old, new) as count:
        assert count > 0, f"DID-NOT-APPLY: {old!r} not found in {_POLICY}"
        result = _run_targeted("history_integrity_shallow_message_names_pin_sha")
        _assert_ran(result)
        assert result.returncode != 0, (
            "Mutation survived: removing pin-SHA read was not caught"
        )


# ---------------------------------------------------------------------------
# #4236: explicit refspec quiet path.
# ---------------------------------------------------------------------------


def test_mutation_disabling_explicit_refspec_quiet_path_is_caught() -> None:
    """Replacing the local_ref != remote_ref guard with False must cause
    test_push_files_warning_is_quiet_for_explicit_refspec_push to fail."""
    old = "        if ref.local_ref != ref.remote_ref:\n            return\n"
    new = (
        "        if False:  # mutation: explicit-refspec quiet path disabled\n"
        "            return\n"
    )
    with _mutated(old, new) as count:
        assert count > 0, f"DID-NOT-APPLY: {old!r} not found in {_POLICY}"
        result = _run_targeted(
            "push_files_warning_is_quiet_for_explicit_refspec_push"
        )
        _assert_ran(result)
        assert result.returncode != 0, (
            "Mutation survived: disabling explicit-refspec quiet path was not caught"
        )


def test_inverted_multi_ref_still_warns_after_fix() -> None:
    """Multi-ref pushes must still warn even after the explicit-refspec fix.

    This is an inverted control: the fix must NOT suppress the warning for a
    push that has two refs (one of which is off-HEAD).
    """
    result = _run_targeted(
        "push_files_warning_emits_for_multi_ref_with_explicit_refspec"
    )
    _assert_ran(result)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Restore verification: baseline must be green after all mutations.
# ---------------------------------------------------------------------------


def test_baseline_still_passes_after_mutations() -> None:
    """Final guard: all targeted tests pass on restored code."""
    result = _run_targeted(
        "push_files_warning or history_integrity_shallow_message"
    )
    _assert_ran(result)
    assert result.returncode == 0, result.stdout + result.stderr
