"""Mutation harness for test_lefthook_ratchet_wiring.py (issue #4041, #4246).

Mutants:
  (a) Comment out the python-lint-count-ratchet job (different ratchet, control).
  (b) Comment out the taste-count-ratchet job.
  (c) Comment out the type-ignore-count-ratchet job.
  (d) Delete --base-ref from the taste-count-ratchet run field only.
  (e) Delete --base-ref from the type-ignore-count-ratchet run field only.

Every mutant must kill at least one test in test_lefthook_ratchet_wiring.py.
A surviving mutant means the test is wrong, not the mutant.

Rules:
- Count occurrences of each pattern before mutating; refuse if != 1 (PATTERN-AMBIGUOUS).
- time.sleep(1.1) after each write to defeat 1-second bytecode mtime granularity.
- Assert byte-identical restore after each mutant run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_LEFTHOOK = Path(__file__).resolve().parents[2] / "lefthook.yml"
_TEST_MODULE = "tests.ci.test_lefthook_ratchet_wiring"
_TEST_FILE = _LEFTHOOK.parent / "tests/ci/test_lefthook_ratchet_wiring.py"

_RUFF_COUNT_NAME_PATTERN = "          - name: python-lint-count-ratchet\n"
_TASTE_NAME_PATTERN = "          - name: taste-count-ratchet\n"
_TYPE_NAME_PATTERN = "          - name: type-ignore-count-ratchet\n"


def _run_wiring_tests() -> tuple[int, str]:
    """Run the wiring test suite and return (returncode, output)."""
    pycache = _TEST_FILE.parent / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--pyargs", _TEST_MODULE, "-x", "-q"],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        errors="replace",
        text=True,
        cwd=str(_LEFTHOOK.parent),
    )
    return result.returncode, result.stdout + result.stderr


def _count_occurrences(text: str, pattern: str) -> int:
    return text.count(pattern)


def _require_unique_pattern(text: str, pattern: str) -> None:
    count = _count_occurrences(text, pattern)
    assert count == 1, f"PATTERN-AMBIGUOUS: {pattern!r} appears {count} times"


def _mutate_and_test(original: bytes, mutated_text: str, mutant_name: str) -> tuple[int, str]:
    """Apply mutation, run tests, restore, verify. Returns (returncode, output)."""
    _LEFTHOOK.write_text(mutated_text, encoding="utf-8")
    time.sleep(1.1)
    rc, output = _run_wiring_tests()
    _LEFTHOOK.write_bytes(original)
    time.sleep(1.1)
    restored = _LEFTHOOK.read_bytes()
    assert restored == original, f"{mutant_name}: restore not byte-identical"
    return rc, output


class TestMutantKillsWiringTests:
    """Each mutant must kill at least one wiring test."""

    def test_mutant_a_comment_out_other_ratchet_survives(self) -> None:
        """Commenting out another ratchet must not fail these wiring tests."""
        original = _LEFTHOOK.read_bytes()
        text = original.decode("utf-8")
        _require_unique_pattern(text, _RUFF_COUNT_NAME_PATTERN)

        mutated = text.replace(
            _RUFF_COUNT_NAME_PATTERN,
            "          # - name: python-lint-count-ratchet\n",
        )
        rc, output = _mutate_and_test(
            original, mutated, "mutant-a-python-lint-count-commented"
        )
        assert rc == 0, (
            f"CONTROL MUTANT DIED: commenting out python-lint-count-ratchet "
            f"failed wiring tests for taste and type-ignore jobs.\n{output}"
        )

    def test_mutant_b_comment_out_taste_job(self) -> None:
        """Commenting out taste-count-ratchet must fail wiring tests."""
        original = _LEFTHOOK.read_bytes()
        text = original.decode("utf-8")
        _require_unique_pattern(text, _TASTE_NAME_PATTERN)

        mutated = text.replace(
            _TASTE_NAME_PATTERN,
            "          # - name: taste-count-ratchet\n",
        )
        rc, output = _mutate_and_test(original, mutated, "mutant-b-taste-commented")
        assert rc != 0, (
            f"MUTANT SURVIVED: commenting out taste-count-ratchet did not fail "
            f"the wiring tests. Tests are not load-bearing.\n{output}"
        )

    def test_mutant_c_comment_out_type_ignore_job(self) -> None:
        """Commenting out type-ignore-count-ratchet must fail wiring tests."""
        original = _LEFTHOOK.read_bytes()
        text = original.decode("utf-8")
        _require_unique_pattern(text, _TYPE_NAME_PATTERN)

        mutated = text.replace(
            _TYPE_NAME_PATTERN,
            "          # - name: type-ignore-count-ratchet\n",
        )
        rc, output = _mutate_and_test(original, mutated, "mutant-c-type-ignore-commented")
        assert rc != 0, (
            f"MUTANT SURVIVED: commenting out type-ignore-count-ratchet did not "
            f"fail the wiring tests.\n{output}"
        )

    def test_mutant_d_delete_base_ref_from_taste_only(self) -> None:
        """Deleting --base-ref from taste-count-ratchet run field must fail."""
        original = _LEFTHOOK.read_bytes()
        text = original.decode("utf-8")

        target = "taste_count_ratchet.py --base-ref origin/main"
        _require_unique_pattern(text, target)

        mutated = text.replace(target, "taste_count_ratchet.py")
        rc, output = _mutate_and_test(original, mutated, "mutant-d-taste-no-base-ref")
        assert rc != 0, (
            f"MUTANT SURVIVED: removing --base-ref from taste job did not fail "
            f"the wiring tests. The test was checking another job's flag.\n{output}"
        )

    def test_mutant_e_delete_base_ref_from_type_ignore_only(self) -> None:
        """Deleting --base-ref from type-ignore-count-ratchet run field must fail."""
        original = _LEFTHOOK.read_bytes()
        text = original.decode("utf-8")

        target = "type_ignore_count_ratchet.py --base-ref origin/main"
        _require_unique_pattern(text, target)

        mutated = text.replace(target, "type_ignore_count_ratchet.py")
        rc, output = _mutate_and_test(original, mutated, "mutant-e-type-no-base-ref")
        assert rc != 0, (
            f"MUTANT SURVIVED: removing --base-ref from type-ignore job did not "
            f"fail the wiring tests.\n{output}"
        )
