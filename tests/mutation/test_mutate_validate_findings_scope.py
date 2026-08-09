"""Mutation harness for the review-scope validator (issue #4020).

Tests two mutations:
1. Remove the ``_LOCATION_FIELD_RE`` bold-marker branch so backtick-wrapped
   bold paths are not extracted -> scope check is silently bypassed.
2. Remove the single-character segment guard in ``_looks_like_path`` so
   ``N/A`` is treated as a file path -> scope check falsely flags prose tokens.

Rules from TESTING-RIGOR.md:
- count occurrences before mutating; refuse ambiguous mutants (PATTERN-AMBIGUOUS)
- delete bytecode caches before each test run
- assert byte-identical restore at end
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_REL = (
    Path(".claude") / "skills" / "review" / "scripts" / "validate_findings_scope.py"
)
TESTS = [
    "tests/skills/review/test_validate_findings_scope.py",
]


def _count(src: bytes, pattern: bytes) -> int:
    return src.count(pattern)


def _run_tests(repo_root: Path) -> subprocess.CompletedProcess[str]:
    pycache = (repo_root / TARGET_REL).parent / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)
    cmd = [sys.executable, "-m", "pytest", "--tb=no", "-q", *TESTS]
    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def _apply_mutant_and_assert_detected(
    repo_root: Path,
    original: bytes,
    original_fragment: bytes,
    mutant_fragment: bytes,
    label: str,
) -> None:
    count = _count(original, original_fragment)
    if count != 1:
        raise AssertionError(
            f"PATTERN-AMBIGUOUS ({label}): expected 1 occurrence, found {count}. "
            "Split into a more specific mutant."
        )

    mutated = original.replace(original_fragment, mutant_fragment, 1)
    assert mutated != original, f"Mutation {label} did not change the file"
    target = repo_root / TARGET_REL

    try:
        target.write_bytes(mutated)
        result = _run_tests(repo_root)
        assert result.returncode != 0, (
            f"MUTANT SURVIVED ({label}): tests passed after the mutation. "
            "The tests do not detect the regression.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        target.write_bytes(original)

    restored = target.read_bytes()
    assert restored == original, f"File not restored byte-identically after mutation {label}"


# ---------------------------------------------------------------------------
# Mutant 1: strip the bold-marker allowance from _LOCATION_FIELD_RE
# (regression of bug 1: bold-wrapped paths no longer extracted)
# ---------------------------------------------------------------------------

MUTANT1_ORIGINAL = (
    b'    r"(?i)\\blocation\\b"              # ``location`` word, case-insensitive\n'
    b'    r"\\s*\\*{0,2}\\s*"                 # optional closing bold markers: ``**``\n'
    b'    r":\\s*"                          # colon separator\n'
)
MUTANT1_REPLACEMENT = (
    b'    r"(?i)\\blocation\\b"              # ``location`` word, case-insensitive\n'
    b'    r"\\s*"                            # mutant: no bold markers allowed\n'
    b'    r":\\s*"                          # colon separator\n'
)

# ---------------------------------------------------------------------------
# Mutant 2: remove the single-character-segment guard in _looks_like_path
# (regression of bug 2: N/A would be treated as a file path again)
# ---------------------------------------------------------------------------

MUTANT2_ORIGINAL = (
    b'        if all(len(seg) <= 1 for seg in segments if seg):\n'
    b'            return False\n'
)
MUTANT2_REPLACEMENT = (
    b'        # mutant: guard removed -- all(len(seg) <= 1 ...) check gone\n'
    b'        pass\n'
)


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    with isolated_mutation_worktree(REPO_ROOT, [TARGET_REL]) as workspace:
        yield workspace.root


def test_mutant1_bold_regex_detected(mutation_repo: Path) -> None:
    original = (mutation_repo / TARGET_REL).read_bytes()
    _apply_mutant_and_assert_detected(
        mutation_repo,
        original,
        MUTANT1_ORIGINAL,
        MUTANT1_REPLACEMENT,
        label="mutant1-bold-regex-stripped",
    )
    # verify tests still pass after restore
    result = _run_tests(mutation_repo)
    assert result.returncode == 0, (
        "Tests failed after restoring original (mutant 1)\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_mutant2_looks_like_path_guard_detected(mutation_repo: Path) -> None:
    original = (mutation_repo / TARGET_REL).read_bytes()
    _apply_mutant_and_assert_detected(
        mutation_repo,
        original,
        MUTANT2_ORIGINAL,
        MUTANT2_REPLACEMENT,
        label="mutant2-path-guard-removed",
    )
    result = _run_tests(mutation_repo)
    assert result.returncode == 0, (
        "Tests failed after restoring original (mutant 2)\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
