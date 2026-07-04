#!/usr/bin/env python3
"""Tests for Issue #2876: pre-push mypy resolves scripts/validation modules.

``scripts/validation/*.py`` use bare intra-package imports
(``from checks_common import ...``) plus a runtime ``sys.path`` self-insert, so
they execute without a package prefix. Under the repo mypy config
(``warn_return_any = true`` + ``ignore_missing_imports = true``), running
``mypy scripts/validation/checks_spec.py`` from the repo root resolves the bare
import to ``Any`` and reports ``no-any-return`` on every ``checks_*`` wrapper
("return exit_code == 0"). The pre-push gate only mypy-checks CHANGED files, so
editing any ``checks_*`` wrapper produced spurious blocking errors.

The fix routes ``scripts/validation/*.py`` through a dedicated bucket
(``PY_FILES_PATHMODULE``) checked one file per invocation with
``MYPYPATH=scripts/validation`` prepended:

- MYPYPATH lets the bare imports resolve, eliminating the false no-any-return.
- One file per invocation avoids "Source file found twice under different
  module names", which fires when a path-reachable module (e.g. checks_common)
  is ALSO imported by another checked file in the same batch.

These tests pin the partition/loop at the script-content level and add a live
mypy smoke test proving (a) the false positive without MYPYPATH, (b) a clean run
with MYPYPATH one-at-a-time, and (c) the "found twice" collision when a
path-reachable module is batched with its importer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"
VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"


def _text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def test_pathmodule_bucket_declared() -> None:
    """pre-push declares the PY_FILES_PATHMODULE partition bucket."""
    text = _text()
    assert "PY_FILES_PATHMODULE" in text, (
        "Expected PY_FILES_PATHMODULE partition variable in pre-push; "
        "Issue #2876 routes scripts/validation modules through a MYPYPATH loop."
    )


def test_validation_files_routed_to_pathmodule() -> None:
    """A case arm routes scripts/validation/*.py into PY_FILES_PATHMODULE."""
    text = _text()
    assert "scripts/validation/*.py)" in text, (
        "Expected a case arm matching scripts/validation/*.py in pre-push; "
        "these modules need MYPYPATH-based resolution (Issue #2876)."
    )
    assert 'PY_FILES_PATHMODULE+=("$_f")' in text, (
        "Expected scripts/validation matches to append to PY_FILES_PATHMODULE."
    )


def test_pathmodule_loop_sets_mypypath_and_is_per_file() -> None:
    """pre-push loops over PY_FILES_PATHMODULE, one mypy call per file, with
    MYPYPATH pointing at scripts/validation."""
    text = _text()
    assert 'for pm_file in "${PY_FILES_PATHMODULE[@]}"; do' in text, (
        "Expected a per-file loop over PY_FILES_PATHMODULE in pre-push."
    )
    assert 'MYPYPATH="$REPO_ROOT/scripts/validation' in text, (
        "Expected MYPYPATH to prepend scripts/validation for pathmodule files."
    )
    # Single-file invocation inside the loop (never batched).
    assert 'mypy "$pm_file"' in text, (
        "Expected the pathmodule loop to invoke mypy on one file at a time."
    )


def test_unique_and_colliding_buckets_preserved() -> None:
    """The Issue #2539 basename partition is not regressed by #2876."""
    text = _text()
    assert "PY_FILES_UNIQUE" in text
    assert "PY_FILES_COLLIDING" in text
    assert 'mypy "${PY_FILES_UNIQUE[@]}"' in text, (
        "Expected the bulk unique-basename mypy invocation to remain."
    )


@pytest.mark.skipif(
    shutil.which("mypy") is None,
    reason="mypy not on PATH; skipping live pathmodule smoke test",
)
def test_checks_wrapper_false_positive_without_mypypath() -> None:
    """Without MYPYPATH, a checks_* wrapper reports no-any-return (the bug)."""
    target = VALIDATION_DIR / "checks_spec.py"
    result = subprocess.run(
        ["mypy", str(target)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = result.stdout + result.stderr
    assert "no-any-return" in combined, (
        "Expected the pre-fix false positive (no-any-return) when mypy runs "
        f"without MYPYPATH; got:\n{combined}"
    )


@pytest.mark.skipif(
    shutil.which("mypy") is None,
    reason="mypy not on PATH; skipping live pathmodule smoke test",
)
def test_checks_wrappers_clean_with_mypypath_per_file() -> None:
    """With MYPYPATH prepended and one file per invocation, the checks_*
    wrappers type-check clean."""
    env = {"MYPYPATH": str(VALIDATION_DIR)}
    for name in (
        "checks_common.py",
        "checks_spec.py",
        "checks_dash.py",
        "checks_tooling.py",
        "checks_plugin.py",
        "checks_coverage.py",
    ):
        target = VALIDATION_DIR / name
        result = subprocess.run(
            ["mypy", str(target)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, **env},
        )
        assert result.returncode == 0, (
            f"mypy on {name} with MYPYPATH should pass one-at-a-time; got:\n"
            f"{result.stdout}{result.stderr}"
        )


@pytest.mark.skipif(
    shutil.which("mypy") is None,
    reason="mypy not on PATH; skipping live pathmodule smoke test",
)
def test_batching_importer_with_imported_module_collides() -> None:
    """Batching a path-reachable module (checks_common) with an importer under
    MYPYPATH triggers 'Source file found twice' -- the reason the loop runs one
    file per invocation. Pins the root cause so behavior changes break loudly.
    """
    env = {"MYPYPATH": str(VALIDATION_DIR)}
    result = subprocess.run(
        [
            "mypy",
            str(VALIDATION_DIR / "checks_spec.py"),
            str(VALIDATION_DIR / "checks_common.py"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, **env},
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "Expected mypy to fail when a path-reachable module is batched with "
        f"its importer under MYPYPATH; exit code was {result.returncode}"
    )
    assert "found twice" in combined.lower(), (
        f"Expected 'Source file found twice' in mypy output; got:\n{combined}"
    )

