"""Shared fixtures for the domain-design tests."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "domain-design" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
