"""Expose the shared test helpers and vendored scripts to the regression suite."""

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-doctor"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
