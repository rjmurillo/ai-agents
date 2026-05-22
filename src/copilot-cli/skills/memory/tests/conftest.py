"""Pytest configuration for memory skill tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add memory_core package to sys.path so tests can import it
_memory_root = Path(__file__).resolve().parent.parent
if str(_memory_root) not in sys.path:
    sys.path.insert(0, str(_memory_root))

# Prevent pytest from collecting source modules whose function names
# start with "test_" (e.g., test_schema_valid, test_forgetful_available).
collect_ignore_glob = ["**/memory_core/*.py", "**/scripts/test_memory_health.py"]
