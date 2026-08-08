"""Mutation harness for the ``What[ \\t]+changed`` claim-section fix.

For each mutant: replace exactly the target pattern in the production code,
run the targeted tests, assert they FAIL (the mutation is detected), then
restore the original and verify byte-identical restoration.

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
TARGET_REL = Path("scripts") / "validation" / "pr_description.py"
# Use -k keyword filter to avoid 100-char line-length limit on node ID strings.
PYTEST_K = "test_issue_4019"

# ---------------------------------------------------------------------------
# The single mutation we test: remove the "What changed" entry from the tuple.
# ---------------------------------------------------------------------------

ORIGINAL_FRAGMENT = b'    r"What[ \\t]+changed",'
MUTANT_FRAGMENT = b'    # r"What[ \\t]+changed",  # mutant: removed'


def _count(src: bytes, pattern: bytes) -> int:
    return src.count(pattern)


def _run_tests(
    repo_root: Path, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    pycache = (repo_root / TARGET_REL).parent / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)
    cmd = [
        sys.executable, "-m", "pytest", "--tb=no", "-q",
        "tests/test_validation_pr_description.py",
        "-k", PYTEST_K,
        *(extra_args or []),
    ]
    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    with isolated_mutation_worktree(REPO_ROOT, [TARGET_REL]) as workspace:
        yield workspace.root


def test_mutant_detected(mutation_repo: Path) -> None:
    target = mutation_repo / TARGET_REL
    original = target.read_bytes()

    count = _count(original, ORIGINAL_FRAGMENT)
    if count != 1:
        raise AssertionError(
            f"PATTERN-AMBIGUOUS: expected 1 occurrence of pattern, found {count}. "
            "Split into a more specific mutant."
        )

    mutated = original.replace(ORIGINAL_FRAGMENT, MUTANT_FRAGMENT, 1)
    assert mutated != original, "Mutation did not change the file"

    try:
        target.write_bytes(mutated)
        result = _run_tests(mutation_repo)
        assert result.returncode != 0, (
            "MUTANT SURVIVED: tests passed after removing 'What[ \\t]+changed' "
            "from _CHANGE_CLAIM_SECTION_NAMES. The tests do not detect the regression.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        target.write_bytes(original)

    # byte-identical restore
    restored = target.read_bytes()
    assert restored == original, "File was not restored byte-identically after mutation"

    # Verify tests pass again after restore
    result_after = _run_tests(mutation_repo)
    assert result_after.returncode == 0, (
        "Tests failed after restoring original file -- unrelated pre-existing failure?\n"
        f"stdout:\n{result_after.stdout}\nstderr:\n{result_after.stderr}"
    )
