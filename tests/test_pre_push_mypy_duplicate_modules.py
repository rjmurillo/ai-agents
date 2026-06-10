#!/usr/bin/env python3
"""Tests for Issue #2539: pre-push mypy partition logic avoids duplicate-module collision.

When a PR changes two Python files with the same basename (e.g.
``.github/scripts/foo.py`` and ``.claude/skills/bar/scripts/foo.py``), mypy
aborts with "Duplicate module named foo" if both are passed in one invocation.

The fix partitions PY_FILES into:
- PY_FILES_UNIQUE: basenames appearing exactly once -- checked in a single fast mypy call
- PY_FILES_COLLIDING: basenames appearing more than once -- each checked individually

These tests pin that partition logic at the script-content level (no subprocess
execution of pre-push itself).  One end-to-end smoke test runs mypy directly to
confirm that the duplicate-module error is real and that per-file invocations
avoid it.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Partition logic exists
# ---------------------------------------------------------------------------


def test_partitions_by_basename() -> None:
    """Arrange/Act: read pre-push text.
    Assert: the script contains logic that partitions PY_FILES by basename into
    a unique set and a colliding set.
    """
    # Arrange
    text = _text()

    # Act -- nothing to run, purely content-level assertion

    # Assert: partition variable names exist
    assert "PY_FILES_UNIQUE" in text, (
        "Expected PY_FILES_UNIQUE partition variable in pre-push; "
        "partition-by-basename logic is missing"
    )
    assert "PY_FILES_COLLIDING" in text, (
        "Expected PY_FILES_COLLIDING partition variable in pre-push; "
        "partition-by-basename logic is missing"
    )
    # Assert: basename is used to build the partition (bash `basename` command
    # or parameter expansion ``${f##*/}``)
    assert ("basename" in text) or ("##*/" in text), (
        "Expected basename extraction (via 'basename' cmd or '##*/' expansion) "
        "in pre-push partition logic"
    )


# ---------------------------------------------------------------------------
# 2. Colliding files are checked per-file (not in one bulk invocation)
# ---------------------------------------------------------------------------


def test_per_file_mypy_for_collisions() -> None:
    """Assert pre-push iterates over PY_FILES_COLLIDING and invokes mypy once
    per file, so no two same-named modules are ever in the same mypy call.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: a loop over PY_FILES_COLLIDING that calls mypy on a single file
    # The loop form is: for col_file in "${PY_FILES_COLLIDING[@]}"; do ... mypy "$col_file"
    assert "PY_FILES_COLLIDING" in text
    # mypy must be called with a single-file variable inside the colliding loop
    # Look for the pattern: mypy "$col_file" or mypy "${col_file}"
    assert ('"$col_file"' in text) or ("${col_file}" in text), (
        "Expected per-file mypy invocation (mypy \"$col_file\") for colliding "
        "files; found neither pattern in pre-push"
    )


# ---------------------------------------------------------------------------
# 3. Non-colliding files still use a single bulk mypy invocation (fast path)
# ---------------------------------------------------------------------------


def test_unique_files_still_bulk_checked() -> None:
    """Assert the fast path: when all basenames are unique, mypy is called once
    with all files, preserving the pre-#2539 single-invocation behavior.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: mypy is called with the full PY_FILES_UNIQUE array
    assert (
        'mypy "${PY_FILES_UNIQUE[@]}"' in text
        or "mypy ${PY_FILES_UNIQUE" in text
    ), (
        "Expected bulk mypy invocation on PY_FILES_UNIQUE array in pre-push; "
        "the non-colliding fast path appears to be missing"
    )


# ---------------------------------------------------------------------------
# 4. Aggregate failure: ALL invocation exits are checked
# ---------------------------------------------------------------------------


def test_aggregate_failure() -> None:
    """Assert that pre-push tracks success/failure across BOTH the unique-files
    mypy call AND every per-colliding-file call, recording a fail only when at
    least one invocation fails.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: a boolean accumulator (e.g. MYPY_OVERALL_PASS or MYPY_FAILED) is
    # present so partial failures are caught.
    assert ("MYPY_OVERALL_PASS" in text) or ("MYPY_FAILED" in text), (
        "Expected an aggregate pass/fail accumulator (MYPY_OVERALL_PASS or "
        "MYPY_FAILED) in pre-push mypy section; a single invocation result is "
        "insufficient when there are multiple mypy calls"
    )
    # Assert: record_pass and record_fail both reference the accumulator region
    # (a record_pass call must follow a successful aggregate check)
    mypy_section_start = text.find("# 7. Python type check (mypy)")
    mypy_section_end = text.find("# 8.", mypy_section_start)
    mypy_section = text[mypy_section_start:mypy_section_end]
    assert "record_pass" in mypy_section, (
        "Expected record_pass in mypy section of pre-push"
    )
    assert "record_fail" in mypy_section, (
        "Expected record_fail in mypy section of pre-push"
    )


# ---------------------------------------------------------------------------
# 5. Tempfile cleanup is preserved for new MYPY_OUTPUT tempfiles
# ---------------------------------------------------------------------------


def test_tempfile_cleanup_preserved() -> None:
    """Assert that any new MYPY_OUTPUT tempfile(s) created for the colliding
    path are added to TEMP_FILES so cleanup() removes them on exit.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: every mktemp result used for mypy output is appended to TEMP_FILES.
    # Count mktemp lines in the mypy section and verify TEMP_FILES+= appears
    # the same number of times in proximity (within the section).
    mypy_section_start = text.find("# 7. Python type check (mypy)")
    mypy_section_end = text.find("# 8.", mypy_section_start)
    mypy_section = text[mypy_section_start:mypy_section_end]

    mktemp_count = mypy_section.count("$(mktemp)")
    temp_files_count = mypy_section.count("TEMP_FILES+=")
    assert mktemp_count > 0, "Expected at least one mktemp in mypy section"
    assert temp_files_count >= mktemp_count, (
        f"Expected at least {mktemp_count} TEMP_FILES+= in mypy section "
        f"(one per mktemp), found {temp_files_count}"
    )


# ---------------------------------------------------------------------------
# End-to-end smoke test: proves WHY the partition is necessary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("mypy") is None,
    reason="mypy not on PATH; skipping live duplicate-module smoke test",
)
def test_collision_reproduction() -> None:
    """Prove that passing two same-basename files to a single mypy invocation
    triggers 'Duplicate module' and that separate invocations succeed.

    This test pins the root cause so that if mypy ever changes behavior the
    test breaks loudly and we can re-evaluate the partition strategy.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        # Arrange: two trivially type-clean files with the same basename
        (dir_a / "foo.py").write_text("x: int = 1\n", encoding="utf-8")
        (dir_b / "foo.py").write_text("y: str = 'hello'\n", encoding="utf-8")

        file_a = str(dir_a / "foo.py")
        file_b = str(dir_b / "foo.py")

        # Act + Assert (negative): single invocation with both files fails with
        # "Duplicate module"
        result_single = subprocess.run(
            ["mypy", file_a, file_b],
            capture_output=True,
            text=True,
        )
        combined = result_single.stdout + result_single.stderr
        assert result_single.returncode != 0, (
            "Expected mypy to fail when given two files with the same basename "
            f"in one invocation; exit code was {result_single.returncode}"
        )
        assert "Duplicate module" in combined or "duplicate module" in combined.lower(), (
            f"Expected 'Duplicate module' in mypy output; got:\n{combined}"
        )

        # Act + Assert (positive): separate invocations each succeed
        result_a = subprocess.run(
            ["mypy", file_a],
            capture_output=True,
            text=True,
        )
        result_b = subprocess.run(
            ["mypy", file_b],
            capture_output=True,
            text=True,
        )
        assert result_a.returncode == 0, (
            f"mypy on {file_a} alone should pass; got:\n{result_a.stdout}{result_a.stderr}"
        )
        assert result_b.returncode == 0, (
            f"mypy on {file_b} alone should pass; got:\n{result_b.stdout}{result_b.stderr}"
        )
