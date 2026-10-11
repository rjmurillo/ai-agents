"""Shared module handle and paths for the detect_infrastructure tests."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/security-detection/detect_infrastructure.py")
matches_pattern = mod.matches_pattern
get_security_risk_level = mod.get_security_risk_level
detect_infrastructure = mod.detect_infrastructure
get_files_from_stdin = mod.get_files_from_stdin
get_staged_files = mod.get_staged_files
CRITICAL_PATTERNS = mod.CRITICAL_PATTERNS
HIGH_PATTERNS = mod.HIGH_PATTERNS
main = mod.main
SKILL_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "security-detection"
)
SKILL_PATH = SKILL_DIR / "SKILL.md"
SCRIPT_PATH = SKILL_DIR / "detect_infrastructure.py"
