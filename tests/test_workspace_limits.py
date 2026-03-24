"""Pytest wrapper for workspace budget enforcement.

Runs on every commit via the pytest CI workflow (AC-3).
Budget: 6.6KB total for injected files, 3KB per file max.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MAX_TOTAL = 6758  # 6.6KB
MAX_PER_FILE = 3072  # 3KB

INJECTED_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
]


def _repo_root() -> Path:
    """Walk up from this file to find the repo root (contains AGENTS.md)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "AGENTS.md").exists():
            return current
        current = current.parent
    pytest.skip("Could not locate repo root")
    return current  # unreachable, satisfies type checker


@pytest.mark.parametrize("filename", INJECTED_FILES)
def test_per_file_limit(filename: str) -> None:
    root = _repo_root()
    filepath = root / filename
    if not filepath.is_file():
        pytest.skip(f"{filename} not found")
    size = filepath.stat().st_size
    assert size <= MAX_PER_FILE, (
        f"{filename} is {size} bytes, exceeds {MAX_PER_FILE} byte limit"
    )


def test_total_budget() -> None:
    root = _repo_root()
    total = 0
    for name in INJECTED_FILES:
        filepath = root / name
        if filepath.is_file():
            total += filepath.stat().st_size
    assert total <= MAX_TOTAL, (
        f"Total workspace size {total} bytes exceeds {MAX_TOTAL} byte budget"
    )
