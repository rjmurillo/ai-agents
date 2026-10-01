"""Pytest configuration for memory skill tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Put the memory skill root on sys.path so tests can import memory_core.
_MEMORY_ROOT = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory"
if str(_MEMORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEMORY_ROOT))
