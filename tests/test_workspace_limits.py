"""Pytest wrapper for workspace budget enforcement.

Runs on every commit via the pytest CI workflow (AC-3).
Budget constants are imported from the authoritative script so the test and
the enforcer always agree (issue #3951).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_workspace_budget import (
    FILE_CEILING_BYTES,
    WORKSPACE_FILES,
)
from scripts.validate_workspace_budget import (
    PER_FILE_BUDGET_BYTES as MAX_PER_FILE,
)
from scripts.validate_workspace_budget import (
    TOTAL_BUDGET_BYTES as MAX_TOTAL,
)

INJECTED_FILES = WORKSPACE_FILES


def _repo_root() -> Path:
    """Walk up from this file to find the repo root (contains AGENTS.md)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "AGENTS.md").exists():
            return current
        current = current.parent
    pytest.skip("Could not locate repo root")
    return current  # unreachable, satisfies type checker


def test_workspace_files_nonempty() -> None:
    """Isolating control: enumerator must return at least one file.

    An empty WORKSPACE_FILES list makes every per-file assertion vacuously
    true (nothing is parametrized) and the total assertion trivially passes.
    """
    assert len(WORKSPACE_FILES) > 0, "WORKSPACE_FILES is empty; gate is disabled"


def test_copilot_instructions_in_gated_set() -> None:
    """Copilot always-on entry point must be in the measured set (issue #3991)."""
    assert ".github/copilot-instructions.md" in WORKSPACE_FILES, (
        ".github/copilot-instructions.md was removed from WORKSPACE_FILES; "
        "the byte gate is now blind to Copilot always-on context growth"
    )


@pytest.mark.parametrize("filename", INJECTED_FILES)
def test_per_file_limit(filename: str) -> None:
    root = _repo_root()
    filepath = root / filename
    if not filepath.is_file():
        pytest.skip(f"{filename} not found")
    size = filepath.stat().st_size
    ceiling = FILE_CEILING_BYTES.get(filename, MAX_PER_FILE)
    assert size <= ceiling, f"{filename} is {size} bytes, exceeds {ceiling} byte ceiling"


def test_total_budget() -> None:
    """Standard workspace files (those without a per-file ratchet) stay within shared pool."""
    root = _repo_root()
    total = 0
    for name in INJECTED_FILES:
        if name in FILE_CEILING_BYTES:
            continue  # files with individual ratchets are measured by test_per_file_limit
        filepath = root / name
        if filepath.is_file():
            total += filepath.stat().st_size
    assert total <= MAX_TOTAL, f"Total workspace size {total} bytes exceeds {MAX_TOTAL} byte budget"


def test_over_ceiling_fails(tmp_path: Path) -> None:
    """A file whose bytes exceed its ceiling must be rejected (negative control)."""
    from scripts.validate_workspace_budget import FileMetric, validate_budget

    oversized = FileMetric(path="fake.md", size_bytes=MAX_PER_FILE + 1, exists=True)
    result = validate_budget([oversized], file_ceilings={})
    assert not result.is_valid, "validate_budget should fail when file exceeds ceiling"
    assert any("fake.md" in e for e in result.errors)


def test_at_ceiling_passes(tmp_path: Path) -> None:
    """A file exactly at its ceiling must pass (boundary positive control)."""
    from scripts.validate_workspace_budget import FileMetric, validate_budget

    at_limit = FileMetric(path="fake.md", size_bytes=MAX_PER_FILE, exists=True)
    result = validate_budget([at_limit], file_ceilings={})
    assert result.is_valid, (
        f"validate_budget should pass when file is exactly at ceiling: {result.errors}"
    )


def test_ratchet_file_excluded_from_total() -> None:
    """Files with per-file ratchets must not inflate the standard total budget."""
    from scripts.validate_workspace_budget import FileMetric, validate_budget

    # Two files: one standard (small), one ratcheted (large).
    # Standard total budget is tiny (1 byte); the ratcheted file must not count
    # toward it or the test would fail spuriously.
    standard = FileMetric(path="a.md", size_bytes=1, exists=True)
    ratcheted = FileMetric(path="b.md", size_bytes=9999, exists=True)
    result = validate_budget(
        [standard, ratcheted],
        total_budget=5,
        per_file_budget=9999,
        file_ceilings={"b.md": 9999},
    )
    assert result.is_valid, "ratcheted file should be excluded from standard total: " + str(
        result.errors
    )
