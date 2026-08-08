"""Mutation control for the PR 4735 QA evidence binding."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _REPO_ROOT / ".claude" / "lib" / "qa_report.py"
_TESTS = ["tests/test_qa_report.py"]


def _clear_bytecode() -> None:
    for cache in (
        _TARGET.parent / "__pycache__",
        _REPO_ROOT / "tests" / "__pycache__",
    ):
        if cache.is_dir():
            shutil.rmtree(cache)


def _run_tests() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_TESTS, "-x", "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode == 4 or "no tests ran" in output.lower():
        raise RuntimeError("Mutation test runner did not execute the target tests")
    return result.returncode, output


def _apply_mutant(original: bytes, old: bytes, new: bytes) -> tuple[bytes, str]:
    count = original.count(old)
    if count == 0:
        return original, "DID-NOT-APPLY"
    if count > 1:
        raise ValueError(f"PATTERN-AMBIGUOUS: target occurs {count} times: {old!r}")
    mutated = original.replace(old, new, 1)
    if mutated == original:
        raise ValueError(f"Mutation produced byte-identical output: {old!r}")
    return mutated, "OK"


def run_mutants() -> None:
    original = _TARGET.read_bytes()
    mutants = [
        (
            "accept non-PASS verdicts",
            b'    if verdict != "PASS" or parsed_verdict != "PASS":',
            b"    if False:  # MUTANT-4735-VERDICT",
            False,
        ),
        (
            "accept unrelated sessions",
            b"    if report.session_log != expected.session_log:",
            b"    if False:  # MUTANT-4735-SESSION",
            False,
        ),
        (
            "accept stale commits",
            b"    if report.commit != expected.commit:",
            b"    if False:  # MUTANT-4735-COMMIT",
            False,
        ),
        (
            "change module description only",
            b"shared by session validators.",
            b"shared by QA validators.",
            True,
        ),
    ]

    dead: list[str] = []
    survived: list[str] = []
    did_not_apply: list[str] = []
    inverted_control_passed = False

    try:
        for name, old, new, should_survive in mutants:
            mutated, status = _apply_mutant(original, old, new)
            if status == "DID-NOT-APPLY":
                did_not_apply.append(name)
                print(f"DID-NOT-APPLY: {name}")
                continue

            _TARGET.write_bytes(mutated)
            _clear_bytecode()
            if _TARGET.read_bytes() == original:
                did_not_apply.append(name)
                print(f"DID-NOT-APPLY: {name}, bytes unchanged")
                continue

            returncode, _output = _run_tests()
            if should_survive:
                if returncode == 0:
                    inverted_control_passed = True
                    print(f"EXPECTED-SURVIVAL: {name}")
                else:
                    dead.append(name)
                    print(f"DEAD-UNEXPECTED: {name}")
            elif returncode == 0:
                survived.append(name)
                print(f"SURVIVED: {name}")
            else:
                dead.append(name)
                print(f"DEAD: {name}")

            _TARGET.write_bytes(original)
            _clear_bytecode()
            if _TARGET.read_bytes() != original:
                raise RuntimeError(f"Restore was not byte-identical: {name}")
    finally:
        _TARGET.write_bytes(original)
        _clear_bytecode()

    print(f"DEAD: {len(dead)}")
    print(f"SURVIVED: {len(survived)}")
    print(f"DID-NOT-APPLY: {len(did_not_apply)}")
    print(f"INVERTED-CONTROL: {'PASS' if inverted_control_passed else 'FAIL'}")

    if did_not_apply:
        raise SystemExit(2)
    if survived or not inverted_control_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_mutants()
