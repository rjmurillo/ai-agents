"""Structure test for the repository-consumer-proof skill template."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates" / "skills" / "repository-consumer-proof.SKILL.md.tmpl"


def _frontmatter() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return text.split("---", 2)[1]


def test_frontmatter_required_fields():
    fm = _frontmatter()
    assert re.search(r"^name: repository-consumer-proof$", fm, re.M)
    assert re.search(r"^version: \S+", fm, re.M)
    assert re.search(r"^description: \S+", fm, re.M)


def test_distribution_is_repo_local():
    assert re.search(r"^  distribution: repo-local$", _frontmatter(), re.M)


def test_no_em_or_en_dashes():
    text = TEMPLATE.read_text(encoding="utf-8")
    for ch in ("\u2014", "\u2013"):
        assert ch not in text
