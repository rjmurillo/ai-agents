"""Mutation harness for issue #4190: semgrep executable pinning in run_semgrep.

Verifies that each load-bearing component of _resolve_semgrep_executable()
and _semgrep_pinned_version() is individually detectable by the test suite.

Rules:
- Count each pattern; exit nonzero with DID-NOT-APPLY when count != 1.
- cmp -s check: fail if mutated bytes are identical to original (no mutation applied).
- sleep(1.1) after every file write to defeat 1-second bytecode mtime cache.
- Restore byte-identically and assert after every mutant.
- Outcomes: DEAD (tests caught it), SURVIVED (tests missed it), DID-NOT-APPLY (pattern absent).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _REPO_ROOT / "scripts" / "security" / "run_semgrep.py"
_TESTS = [
    "tests/test_run_semgrep_pinning.py",
]


def _run_tests() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_TESTS, "-x", "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
    )
    return result.returncode


def _apply_mutant(original: bytes, old: bytes, new: bytes) -> tuple[bytes, str]:
    """Return mutated bytes and a status string."""
    count = original.count(old)
    if count == 0:
        return original, "DID-NOT-APPLY"
    if count > 1:
        raise ValueError(
            f"PATTERN-AMBIGUOUS: pattern appears {count} times (need exactly 1): {old!r}"
        )
    mutated = original.replace(old, new, 1)
    if mutated == original:
        raise ValueError(f"Mutation produced byte-identical output for: {old!r}")
    return mutated, "OK"


def run_mutants() -> None:
    original_bytes = _TARGET.read_bytes()

    mutants = [
        (
            "remove venv sibling semgrep check",
            b"    sibling = Path(sys.executable).parent / sibling_name\n"
            b"    if sibling.is_file() and os.access(sibling, os.X_OK):\n"
            b"        return _verify_pinned_version(str(sibling), repo_root)",
            b"    sibling = Path(sys.executable).parent / sibling_name\n"
            b"    if False:  # MUTANT-DELETED-4190\n"
            b"        return _verify_pinned_version(str(sibling), repo_root)",
        ),
        (
            "remove version mismatch check in _verify_pinned_version",
            b"    if version != pinned:\n"
            b"        raise _SemgrepExecutableError(\n"
            b"            f\"semgrep version mismatch: pyproject.toml pins {pinned!r}, \"\n"
            b"            f\"but {executable} reports {version!r}. \"\n"
            b"            f\"Reinstall the pin with: {_INSTALL_HINT}\"\n"
            b"        )",
            b"    if False:  # MUTANT-DELETED-4190\n"
            b"        raise _SemgrepExecutableError(\n"
            b"            f\"semgrep version mismatch: pyproject.toml pins {pinned!r}, \"\n"
            b"            f\"but {executable} reports {version!r}. \"\n"
            b"            f\"Reinstall the pin with: {_INSTALL_HINT}\"\n"
            b"        )",
        ),
        (
            "weaken version regex to match any semgrep line",
            b'        r\'^\\s*"semgrep==([^"]+)",\\s*$\',',
            b'        r\'"semgrep==([^"]+)",\',  # MUTANT-DELETED-4190',
        ),
        (
            "suppress _SemgrepExecutableError on no PATH semgrep",
            b"    resolved = shutil.which(\"semgrep\")\n"
            b"    if resolved is None:\n"
            b"        raise FileNotFoundError(\"semgrep not found on PATH\")",
            b"    resolved = shutil.which(\"semgrep\")\n"
            b"    if resolved is None:\n"
            b"        resolved = \"semgrep\"  # MUTANT-DELETED-4190",
        ),
    ]

    dead: list[str] = []
    survived: list[str] = []
    did_not_apply: list[str] = []

    for name, old, new in mutants:
        print(f"\n--- Mutant: {name} ---")
        mutated, status = _apply_mutant(original_bytes, old, new)

        if status == "DID-NOT-APPLY":
            did_not_apply.append(name)
            print("  DID-NOT-APPLY: pattern not found in target file")
            continue

        _TARGET.write_bytes(mutated)
        time.sleep(1.1)

        on_disk = _TARGET.read_bytes()
        if on_disk == original_bytes:
            _TARGET.write_bytes(original_bytes)
            did_not_apply.append(name)
            print("  DID-NOT-APPLY: file byte-identical after write")
            continue

        rc = _run_tests()
        if rc == 0:
            survived.append(name)
            print("  SURVIVED: tests passed when they should have failed")
        else:
            dead.append(name)
            print(f"  DEAD: tests caught the mutation (exit {rc})")

        _TARGET.write_bytes(original_bytes)
        time.sleep(1.1)
        restored = _TARGET.read_bytes()
        assert restored == original_bytes, f"Restore was not byte-identical for: {name}"

    print(f"\n{'='*60}")
    print(f"DEAD:          {len(dead)}")
    print(f"SURVIVED:      {len(survived)}")
    print(f"DID-NOT-APPLY: {len(did_not_apply)}")

    if did_not_apply:
        print("\nDID-NOT-APPLY (patterns not found -- verify target still contains them):")
        for msg in did_not_apply:
            print(f"  {msg}")

    if survived:
        print("\nSURVIVING MUTANTS (test suite did not detect):")
        for msg in survived:
            print(f"  {msg}")
        sys.exit(1)

    if did_not_apply:
        print("\nDID-NOT-APPLY mutations present -- target may have changed.")
        sys.exit(2)

    print("\nAll mutants killed. Tests are load-bearing.")


if __name__ == "__main__":
    run_mutants()
