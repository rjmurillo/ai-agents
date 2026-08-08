"""Mutation harness for check_subprocess_encoding.py (issue #4261).

Tests three mutations, each of which should cause the test suite to go RED.
Also includes one cosmetic mutation that must SURVIVE (negative control).

Purges __pycache__ between mutants to prevent CPython's mtime/size-based
bytecode cache from serving stale bytecodes.

Exit 0 = all mutations killed correctly.
Exit 1 = a mutation survived (false survivor) or a control was killed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _purge_cache(root: Path) -> None:
    for d in root.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def _apply_mutation(source: str, original: str, replacement: str) -> str:
    match_count = source.count(original)
    if match_count == 0:
        raise ValueError(f"Mutation text not found in source:\n  {original!r}")
    if match_count != 1:
        raise ValueError(
            f"Mutation text matched {match_count} times; expected exactly 1:\n  {original!r}"
        )
    return source.replace(original, replacement, 1)


def test_apply_mutation_rejects_ambiguous_target() -> None:
    with pytest.raises(ValueError, match="expected exactly 1"):
        _apply_mutation("needle\nneedle\n", "needle", "replacement")


def _run_tests(repo_root: Path) -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/validation/test_check_subprocess_encoding.py",
            "-x",
            "-q",
            "--tb=no",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
    )
    return result.returncode


def _run_mutation(
    name: str,
    original: str,
    replacement: str,
    must_kill: bool,
    fail_msg: str | None,
    original_source: str,
    checker: Path,
    repo_root: Path,
    failures: list[str],
) -> None:
    print(f"\n=== {name} ===")
    try:
        mutated = _apply_mutation(original_source, original, replacement)
    except ValueError as exc:
        print(f"  SKIP: {exc}")
        if must_kill:
            failures.append(f"{name}: mutation did not apply (DID-NOT-APPLY)")
        return

    checker.write_text(mutated, encoding="utf-8")
    _purge_cache(repo_root)
    try:
        rc = _run_tests(repo_root)
    finally:
        checker.write_text(original_source, encoding="utf-8")
        _purge_cache(repo_root)

    restored = checker.read_text(encoding="utf-8")
    if restored != original_source:
        print("  ERROR: restore failed")
        failures.append(f"{name}: restore failed")
        return

    if must_kill:
        if rc in (1, 2):
            print(f"  KILLED (rc={rc})")
        elif rc == 4:
            print(f"  FALSE KILL: pytest exit 4 (collection error, not a kill) rc={rc}")
            failures.append(f"{name}: pytest exit 4 is a collection error, not a kill")
        elif rc == 5:
            print(f"  FALSE KILL: pytest exit 5 (no tests collected, not a kill) rc={rc}")
            failures.append(f"{name}: pytest exit 5 means no tests collected, not a kill")
        else:
            print(f"  SURVIVED (rc={rc}) -- {fail_msg}")
            failures.append(f"{name}: {fail_msg}")
    else:
        if rc == 0:
            print("  SURVIVED (as expected, rc=0)")
        else:
            print(f"  KILLED (rc={rc}) -- cosmetic mutation should not kill tests")
            failures.append(f"{name}: cosmetic mutation killed tests (false kill)")


def main() -> int:
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
    )

    checker = repo_root / "scripts" / "validation" / "check_subprocess_encoding.py"
    if not checker.is_file():
        print(f"ERROR: checker not found at {checker}", file=sys.stderr)
        return 1

    original_source = checker.read_text(encoding="utf-8")
    failures: list[str] = []

    mutations = [
        # Mutation 1: disable the text= check (replace True with False in _uses_text_mode)
        (
            "mutation-1-disable-text-check",
            'text_enabled = (\n'
            '        _is_true_literal(_keyword_value(call, "text"))\n'
            '        or _is_true_literal(_keyword_value(call, "universal_newlines"))\n'
            '        or _is_true_literal(_keyword_value(call, "capture_output"))\n'
            '        or pipe_capture\n'
            '    )',
            "text_enabled = False",
            True,  # must_kill
            "test_text_only_flagged: text= check disabled but test did not catch it",
        ),
        # Mutation 2: disable the errors= detection (always claim errors= present)
        (
            "mutation-2-disable-errors-detection",
            'if _has_keyword(call, "errors"):\n'
            "        return False",
            "if False:\n"
            "        return False",
            True,
            (
                "test_known_bad_input_exits_nonzero: errors= detection disabled"
                " but test did not catch it"
            ),
        ),
        # Mutation 3: invert the violation condition (flag compliant calls instead of bad ones)
        (
            "mutation-3-invert-violation-condition",
            "if not unconditional and not text_enabled:",
            "if not unconditional and text_enabled:",
            True,
            "inverted condition: flags compliant calls instead of bad ones",
        ),
        # Mutation 4: drop stdout/stderr PIPE capture detection.
        (
            "mutation-4-disable-pipe-capture",
            "or pipe_capture",
            "or False",
            True,
            "pipe capture detection disabled but tests did not catch it",
        ),
        # Cosmetic mutation (negative control): must SURVIVE
        (
            "cosmetic-no-kill",
            "text-mode UTF-8 must pair",
            "text mode UTF-8 must pair",
            False,
            None,
        ),
    ]

    for name, original, replacement, must_kill, fail_msg in mutations:
        _run_mutation(
            name, original, replacement, must_kill, fail_msg,
            original_source, checker, repo_root, failures,
        )

    # Verify baseline green
    _purge_cache(repo_root)
    print("\n=== baseline green check ===")
    rc = _run_tests(repo_root)
    if rc != 0:
        print(f"  FAIL: baseline not green after restore (rc={rc})")
        failures.append("baseline: not green after all restores")
    else:
        print("  PASS")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"\nAll {len(mutations)} mutations handled correctly.")
    return 0


@pytest.mark.timeout(300)
def test_mutation_harness() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
