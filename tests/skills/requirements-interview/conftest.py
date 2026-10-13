"""Make the audit-mode helpers importable; see audit_paths.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import audit_paths  # noqa: F401  (side effect: puts the skill scripts on sys.path)
