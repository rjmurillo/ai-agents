"""Reproduction and fix for stale-bytecode in mutation harnesses (issue #3896).

## Problem

CPython validates pyc caches using two fields: ``st_mtime`` truncated to whole
seconds and ``st_size`` in bytes. A same-length mutation leaves ``st_size``
unchanged. If the restore write lands in the same integer second the cache was
written, ``st_mtime`` also matches and the stale cache is reused.

This means a mutation harness that rewrites a source file with a same-length
edit and runs pytest within one second may silently run the ORIGINAL bytecode
rather than the mutant.

## Key finding

``PYTHONDONTWRITEBYTECODE=1`` prevents writing NEW .pyc files but does NOT
prevent reading existing ones. If a .pyc is already present with a matching
(mtime, size) pair, the interpreter still uses it. The required fix is to
PURGE the ``__pycache__`` directory before each subprocess invocation.
Setting ``PYTHONDONTWRITEBYTECODE=1`` additionally prevents the mutant's
bytecode from poisoning the NEXT run (cross-mutant contamination), but it
cannot substitute for the purge.

## Structure

- ``test_before__stale_cache_hides_mutation``: demonstrates the defect.
  Creates a .pyc, mutates same-length, runs child without fix. Child still
  sees original value, proving stale cache was used.

- ``test_after__pycache_purge_sees_mutation``: the primary fix. Purges
  ``__pycache__`` before the child run. Child sees mutated value.

- ``test_after__purge_plus_no_write_prevents_cross_contamination``: combined
  fix. Purge + ``PYTHONDONTWRITEBYTECODE=1``. Verifies that the mutant's
  bytecode is neither read (purge) nor written (no-write flag), leaving the
  next run's cache clean.

- ``test_pythondontwritebytecode_alone_insufficient``: documents that the
  flag alone does not fix the problem when a stale .pyc already exists.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _write_module(path: Path, return_val: str) -> None:
    """Write a tiny Python module whose ``identity()`` returns ``return_val``.

    All variants must have the same byte length so ``st_size`` is unchanged
    between original and mutant.
    """
    assert len(return_val) == 1, "return_val must be exactly one char for same-length test"
    src = f'def identity() -> str:\n    return "{return_val}"\n'
    path.write_text(src, encoding="utf-8")


def _prime_cache(module_path: Path) -> None:
    """Import the module in a child to create a .pyc cache entry."""
    probe = (
        f"import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('m', {str(module_path)!r}); "
        f"m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True, encoding="utf-8",
        check=True,
    )
    assert result.returncode == 0, result.stderr


def _read_identity(module_path: Path, env: dict[str, str] | None = None) -> str:
    """Import the module in a child process and return identity()."""
    probe = (
        f"import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('m', {str(module_path)!r}); "
        f"m = importlib.util.module_from_spec(spec); "
        f"spec.loader.exec_module(m); print(m.identity(), end='')"
    )
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True, encoding="utf-8",
        env=merged_env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# BEFORE: stale cache hides same-length mutation
# ---------------------------------------------------------------------------


def test_before__stale_cache_hides_mutation(tmp_path: Path) -> None:
    """Without a fix, a same-length mutation with matching mtime uses stale bytecode.

    The child subprocess reads the ORIGINAL return value ("a") even though the
    source was mutated to return "b", because mtime and size both match.

    The mtime match is forced deterministically with ``os.utime`` so the test
    passes regardless of system clock resolution or load.
    """
    module = tmp_path / "subject.py"
    _write_module(module, "a")  # original: identity() -> "a"
    # Record the source mtime BEFORE priming so we can restore it after mutating.
    original_mtime = os.stat(module).st_mtime
    _prime_cache(module)  # .pyc records original_mtime

    # Verify .pyc was created
    pycache = module.parent / "__pycache__"
    if not pycache.exists():
        return  # no .pyc written (env already has PYTHONDONTWRITEBYTECODE)

    # Mutate same-length: "a" -> "b" (st_size unchanged)
    _write_module(module, "b")
    # Force the mtime back to original so the .pyc header still matches.
    # This reproduces the defect deterministically without relying on the write
    # landing in the same wall-clock second as the cache prime.
    os.utime(module, (original_mtime, original_mtime))

    # Run WITHOUT the fix
    result = _read_identity(module)

    # With stale bytecode the child still sees "a" (the pre-mutation value).
    assert result == "a", (
        f"Expected stale cache to return 'a' but got {result!r}. "
        "The stale-bytecode defect was not reproduced."
    )


# ---------------------------------------------------------------------------
# EDGE: PYTHONDONTWRITEBYTECODE alone does NOT fix the existing-cache problem
# ---------------------------------------------------------------------------


def test_pythondontwritebytecode_alone_insufficient(tmp_path: Path) -> None:
    """PYTHONDONTWRITEBYTECODE=1 does not prevent reading an existing .pyc.

    The flag stops new cache files from being WRITTEN but the import machinery
    still reads and validates existing .pyc headers. A matching (mtime, size)
    entry is reused even under the flag.
    """
    module = tmp_path / "subject.py"
    _write_module(module, "a")
    original_mtime = os.stat(module).st_mtime
    _prime_cache(module)

    pycache = module.parent / "__pycache__"
    if not pycache.exists():
        return  # no .pyc, can't show this edge case

    _write_module(module, "b")
    os.utime(module, (original_mtime, original_mtime))

    # Flag set, but existing .pyc still wins
    result = _read_identity(module, env={"PYTHONDONTWRITEBYTECODE": "1"})

    # Still reads "a" from the stale cache, confirming the flag alone is insufficient
    assert result == "a", (
        f"Expected stale 'a' with flag-only (no purge) but got {result!r}. "
        "The existing .pyc was not present or was already invalidated."
    )


# ---------------------------------------------------------------------------
# AFTER fix: purge __pycache__ before the run
# ---------------------------------------------------------------------------


def test_after__pycache_purge_sees_mutation(tmp_path: Path) -> None:
    """Purging __pycache__ before the run forces re-compilation from .py.

    This is the primary fix. Removing the .pyc directory means the interpreter
    has no cache to reuse and must read the .py file directly.
    """
    module = tmp_path / "subject.py"
    _write_module(module, "a")
    _prime_cache(module)

    # Mutate same-length
    _write_module(module, "b")

    # Purge .pyc caches before running the harness
    pycache = module.parent / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)

    result = _read_identity(module)

    assert result == "b", (
        f"Expected 'b' after pycache purge but got {result!r}. The fix is not working."
    )


# ---------------------------------------------------------------------------
# AFTER fix: purge + PYTHONDONTWRITEBYTECODE prevents cross-run contamination
# ---------------------------------------------------------------------------


def test_after__purge_plus_no_write_prevents_cross_contamination(
    tmp_path: Path,
) -> None:
    """Purge + PYTHONDONTWRITEBYTECODE=1 is the complete two-run fix.

    Purge ensures the current run reads the mutated source.
    PYTHONDONTWRITEBYTECODE=1 ensures the mutant's bytecode is not written
    to disk, preventing the next mutant's baseline run from reading it.

    This test simulates two consecutive mutations and verifies both are
    observed cleanly.
    """
    module = tmp_path / "subject.py"
    fix_env = {"PYTHONDONTWRITEBYTECODE": "1"}

    # Run 1: mutation a -> b
    _write_module(module, "a")
    _prime_cache(module)
    _write_module(module, "b")

    pycache = module.parent / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)

    result1 = _read_identity(module, env=fix_env)
    assert result1 == "b", f"Run 1 expected 'b' but got {result1!r}"

    # Restore to "a", then mutate to "c" (second mutation cycle)
    _write_module(module, "a")
    _write_module(module, "c")

    # Because PYTHONDONTWRITEBYTECODE=1 was set in run 1, no .pyc was written.
    # No purge needed (no stale cache exists). Run 2 should observe "c".
    result2 = _read_identity(module, env=fix_env)
    assert result2 == "c", f"Run 2 expected 'c' but got {result2!r}"
