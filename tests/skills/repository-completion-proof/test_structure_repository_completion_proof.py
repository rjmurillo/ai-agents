"""Structure test for the repository-completion-proof skill."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = ROOT / ".claude" / "skills" / "repository-completion-proof" / "SKILL.md"


def _frontmatter() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return text.split("---", 2)[1]


def test_skill_md_exists():
    assert SKILL_MD.is_file()


def test_frontmatter_required_fields():
    fm = _frontmatter()
    assert re.search(r"^name: repository-completion-proof$", fm, re.M)
    assert re.search(r"^version: \S+", fm, re.M)
    assert re.search(r"^description: \S+", fm, re.M)


def test_distribution_is_repo_local():
    assert re.search(r"^\s+distribution: repo-local$", _frontmatter(), re.M)
