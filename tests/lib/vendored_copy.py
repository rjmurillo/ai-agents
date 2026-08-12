"""Helpers for building cache-free vendored plugin fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
)


def copy_vendored_entry(source: Path, target: Path) -> None:
    """Copy one vendored entry without mutable runtime caches."""
    if source.is_dir():
        shutil.copytree(source, target, ignore=_COPY_IGNORE)
        return
    shutil.copy2(source, target)
