"""Mutation harness for the ``What[ \\t]+changed`` claim-section fix.

For each mutant: replace exactly the target pattern in the production code,
run the targeted tests, assert they FAIL (the mutation is detected), then
restore the original and verify byte-identical restoration.

Rules from TESTING-RIGOR.md:
- count occurrences before mutating; refuse ambiguous mutants (PATTERN-AMBIGUOUS)
- sleep(1.1) after each write to defeat 1-second bytecode mtime granularity
- assert byte-identical restore at end
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "scripts" / "validation" / "pr_description.py"
TESTS = [
    "tests/test_validation_pr_description.py::TestValidatePRDescription::test_issue_4019_what_changed_heading_extracts_inline_code[## What changed]",
    "tests/test_validation_pr_description.py::TestValidatePRDescription::test_issue_4019_what_changed_fake_path_is_flagged_as_critical[## What changed]",
    "tests/test_validation_pr_description.py::TestValidatePRDescription::test_issue_4019_what_changed_is_distinct_from_summary",
]

# ---------------------------------------------------------------------------
# The single mutation we test: remove the "What changed" entry from the tuple.
# ---------------------------------------------------------------------------

ORIGINAL_FRAGMENT = b'    r"What[ \\t]+changed",'
MUTANT_FRAGMENT = b'    # r"What[ \\t]+changed",  # mutant: removed'


def _count(src: bytes, pattern: bytes) -> int:
    return src.count(pattern)


def _run_tests(extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, "-m", "pytest", "--tb=no", "-q",
        *TESTS,
        *(extra_args or []),
    ]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)


def test_mutant_detected() -> None:
    original = TARGET.read_bytes()

    count = _count(original, ORIGINAL_FRAGMENT)
    if count != 1:
        raise AssertionError(
            f"PATTERN-AMBIGUOUS: expected 1 occurrence of pattern, found {count}. "
            "Split into a more specific mutant."
        )

    mutated = original.replace(ORIGINAL_FRAGMENT, MUTANT_FRAGMENT, 1)
    assert mutated != original, "Mutation did not change the file"

    try:
        TARGET.write_bytes(mutated)
        time.sleep(1.1)  # defeat 1-second bytecode mtime granularity

        result = _run_tests()
        assert result.returncode != 0, (
            "MUTANT SURVIVED: tests passed after removing 'What[ \\t]+changed' "
            "from _CHANGE_CLAIM_SECTION_NAMES. The tests do not detect the regression.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        TARGET.write_bytes(original)
        time.sleep(1.1)

    # byte-identical restore
    restored = TARGET.read_bytes()
    assert restored == original, "File was not restored byte-identically after mutation"

    # Verify tests pass again after restore
    result_after = _run_tests()
    assert result_after.returncode == 0, (
        "Tests failed after restoring original file -- unrelated pre-existing failure?\n"
        f"stdout:\n{result_after.stdout}\nstderr:\n{result_after.stderr}"
    )
