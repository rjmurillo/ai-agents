"""Scratch-worktree scaffolding for the ADR debate-log mutation harness.

Split out of ``test_mutate_adr_debate_evidence.py`` when that module crossed the
500-line file-size rule. The seam is the obvious one: everything here is the
machinery that applies a mutant and reports DEAD or SURVIVED, and everything
left there is the mutants themselves plus the guards over them.

The arity guard stays in the test module on purpose. It parses its own
``__file__`` for tests taking the ``scratch_worktree`` fixture, so it has to
live beside the tests it counts.

Issue #5205.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET_REL = Path("scripts") / "validation" / "git_hook_policy.py"
# The two defects are only observable through the suite written for #5205.
# Both halves of the split suite. The boundary module is not optional here:
# M6's killer, test_invalid_utf8_bytes_do_not_inflate_toward_the_byte_floor,
# lives there, so running only the sibling would report M6 SURVIVED.
_TESTS = [
    "tests/validation/test_git_hook_policy_adr_debate_evidence.py",
    "tests/validation/test_git_hook_policy_adr_debate_boundaries.py",
    "tests/validation/test_git_hook_policy_adr_debate_mirrors.py",
    "tests/validation/test_git_hook_policy_adr_debate_discovery.py",
]

_OUTCOME_DEAD = "DEAD"
_OUTCOME_SURVIVED = "SURVIVED"
_OUTCOME_DID_NOT_APPLY = "DID-NOT-APPLY"

# Same ordering contract as the sibling harness: the outer cap MUST exceed the
# inner one, or pytest-timeout interrupts inside subprocess.communicate and the
# failure names no command (issue #5102). The inner suite here is
# four files of 70 cases total, well under the sibling's ~943, so these caps
# carry wide margin.
_INNER_SUBPROCESS_TIMEOUT_SECONDS = 300
_OUTER_TEST_TIMEOUT_SECONDS = 360


def _run_tests_in(wt_path: Path) -> subprocess.CompletedProcess[str]:
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
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=_INNER_SUBPROCESS_TIMEOUT_SECONDS,
    )


def _assert_suite_ran(result: subprocess.CompletedProcess[str], label: str) -> None:
    assert result.returncode != 4, (
        f"{label}: pytest exited 4 (file or directory not found). "
        f"Suite was never collected.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "no tests ran" not in result.stdout.lower(), (
        f"{label}: no tests were collected.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _mutate(wt_path: Path, original: bytes, before: bytes, after: bytes, label: str) -> bytes:
    count = original.count(before)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} ({label}): literal not found in target. "
            "The file was changed; update this harness."
        )
    if count > 1:
        raise AssertionError(f"PATTERN-AMBIGUOUS ({label}): expected 1 occurrence, found {count}.")
    mutated = original.replace(before, after, 1)
    assert mutated != original, f"Mutation {label} produced a byte-identical file"
    (wt_path / _TARGET_REL).write_bytes(mutated)
    return mutated


def _run_mutant(
    wt_path: Path, original: bytes, before: bytes, after: bytes, label: str
) -> subprocess.CompletedProcess[str]:
    _mutate(wt_path, original, before, after, label)
    wt_target = wt_path / _TARGET_REL
    try:
        result = _run_tests_in(wt_path)
    finally:
        wt_target.write_bytes(original)
        assert wt_target.read_bytes() == original, (
            f"{label}: scratch worktree target was not restored to original bytes"
        )
    _assert_suite_ran(result, label)
    return result


def _apply_positive_mutant(
    wt_path: Path, original: bytes, before: bytes, after: bytes, label: str
) -> str:
    result = _run_mutant(wt_path, original, before, after, label)
    assert result.returncode != 0, (
        f"MUTANT SURVIVED ({label}): suite passed after mutation. "
        f"Tests do not detect the regression.\nstdout:\n{result.stdout}"
    )
    return _OUTCOME_DEAD


def _active_target_unmodified() -> bool:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", str(_TARGET_REL)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()
