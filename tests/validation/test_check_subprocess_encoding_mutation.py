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


def _purge_cache(root: Path) -> None:
    for d in root.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def _apply_mutation(source: str, original: str, replacement: str) -> str:
    if original not in source:
        raise ValueError(f"Mutation text not found in source:\n  {original!r}")
    return source.replace(original, replacement, 1)


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
            'return "text" in keywords or "encoding" in keywords',
            'return "encoding" in keywords',
            True,  # must_kill
            "test_text_only_flagged: text= check disabled but test did not catch it",
        ),
        # Mutation 2: disable the errors= detection (always claim errors= present)
        (
            "mutation-2-disable-errors-detection",
            'return "errors" in keywords',
            "return True  # mutation: pretend errors= is always present",
            True,
            (
                "test_known_bad_input_exits_nonzero: errors= detection disabled"
                " but test did not catch it"
            ),
        ),
        # Mutation 3: invert the violation condition (flag compliant calls instead of bad ones)
        (
            "mutation-3-invert-violation-condition",
            "if _uses_text_mode(keywords) and not _has_errors_kwarg(keywords):",
            "if _uses_text_mode(keywords) and _has_errors_kwarg(keywords):",
            True,
            "inverted condition: flags compliant calls instead of bad ones",
        ),
        # Cosmetic mutation (negative control): must SURVIVE
        (
            "cosmetic-no-kill",
            "uses text mode but omits errors=; ",
            "uses text-mode but omits errors=; ",
            False,
            None,
        ),
    ]

    for name, original, replacement, must_kill, fail_msg in mutations:
        print(f"\n=== {name} ===")
        try:
            mutated = _apply_mutation(original_source, original, replacement)
        except ValueError as exc:
            print(f"  SKIP: {exc}")
            if must_kill:
                failures.append(f"{name}: mutation did not apply (DID-NOT-APPLY)")
            continue

        checker.write_text(mutated, encoding="utf-8")
        _purge_cache(repo_root)

        rc = _run_tests(repo_root)

        checker.write_text(original_source, encoding="utf-8")
        _purge_cache(repo_root)

        # Verify restore applied (size check)
        restored = checker.read_text(encoding="utf-8")
        if restored != original_source:
            print("  ERROR: restore failed")
            failures.append(f"{name}: restore failed")
            continue

        if must_kill:
            if rc in (1, 2):
                print(f"  KILLED (rc={rc})")
            elif rc == 4:
                print(f"  FALSE KILL: pytest exit 4 (collection error, not a kill) rc={rc}")
                failures.append(f"{name}: pytest exit 4 is a collection error, not a kill")
            else:
                print(f"  SURVIVED (rc={rc}) -- {fail_msg}")
                failures.append(f"{name}: {fail_msg}")
        else:
            # Cosmetic: must NOT kill (tests should still pass)
            if rc == 0:
                print("  SURVIVED (as expected, rc=0)")
            else:
                print(f"  KILLED (rc={rc}) -- cosmetic mutation should not kill tests")
                failures.append(f"{name}: cosmetic mutation killed tests (false kill)")

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


if __name__ == "__main__":
    raise SystemExit(main())
