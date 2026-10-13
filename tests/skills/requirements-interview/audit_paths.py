"""Paths shared by the audit-mode tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "requirements-interview"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
