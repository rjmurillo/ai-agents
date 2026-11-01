"""Frontmatter structure test for the repository-pr-recovery skill."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = ROOT / ".claude" / "skills" / "repository-pr-recovery" / "SKILL.md"


def _frontmatter() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return text.split("---", 2)[1]


def test_frontmatter_name_version_description():
    fm = _frontmatter()
    assert re.search(r"^name: repository-pr-recovery$", fm, re.M)
    assert re.search(r"^version: \d+\.\d+\.\d+$", fm, re.M)
    assert re.search(r"^description: \S", fm, re.M)


def test_distribution_is_repo_local():
    assert re.search(r"^\s+distribution: repo-local$", _frontmatter(), re.M)
