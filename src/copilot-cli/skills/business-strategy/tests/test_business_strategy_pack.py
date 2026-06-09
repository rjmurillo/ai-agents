"""Structural tests for the business-strategy skill pack (issue #1784).

A prompt/reference skill has no scripts to unit-test, so the contract is
structural: the SKILL.md frontmatter is valid, every reference the router points
to exists, each reference is substantive, and nothing in the pack carries a
prohibited em/en dash (universal.md MUST).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PACK = Path(__file__).resolve().parents[1]
_SKILL = _PACK / "SKILL.md"
_REFS = _PACK / "references"

_EXPECTED_BOOKS = {
    "mom-test",
    "four-steps",
    "lean-startup",
    "obviously-awesome",
    "crossing-the-chasm",
    "blue-ocean-strategy",
    "monetizing-innovation",
    "100m-offers",
    "100m-leads",
    "spin-selling",
    "influence",
    "traction",
    "storybrand",
    "made-to-stick",
}


def _frontmatter(text: str) -> dict[str, str]:
    block = re.match(r"^---\n(.*?)\n---", text, re.S)
    assert block, "SKILL.md must open with a YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in block.group(1).splitlines():
        m = re.match(r"^([a-zA-Z_-]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2)
    return fields


def test_skill_md_exists():
    assert _SKILL.is_file()


def test_frontmatter_has_required_fields():
    fm = _frontmatter(_SKILL.read_text(encoding="utf-8"))
    assert fm.get("name") == "business-strategy"
    assert fm.get("description"), "description is required"


def test_router_references_all_fourteen_books():
    text = _SKILL.read_text(encoding="utf-8")
    referenced = {m for m in re.findall(r"references/([a-z0-9-]+)\.md", text)}
    assert _EXPECTED_BOOKS <= referenced, f"router missing: {_EXPECTED_BOOKS - referenced}"


def test_every_referenced_file_exists():
    text = _SKILL.read_text(encoding="utf-8")
    for stem in re.findall(r"references/([a-z0-9-]+\.md)", text):
        assert (_REFS / stem).is_file(), f"missing reference: {stem}"


def test_no_orphan_references():
    text = _SKILL.read_text(encoding="utf-8")
    referenced = {f"{m}.md" for m in re.findall(r"references/([a-z0-9-]+)\.md", text)}
    present = {p.name for p in _REFS.glob("*.md")}
    assert present <= referenced, f"orphan reference files: {present - referenced}"


@pytest.mark.parametrize("book", sorted(_EXPECTED_BOOKS))
def test_reference_is_substantive(book: str):
    body = (_REFS / f"{book}.md").read_text(encoding="utf-8")
    assert len(body) > 1500, f"{book}.md is too thin to be a useful distillation"
    assert body.lstrip().startswith("#"), f"{book}.md must open with a heading"


def test_pack_has_no_prohibited_dashes():
    for path in _PACK.rglob("*.md"):
        data = path.read_bytes()
        assert "—".encode() not in data, f"em dash in {path.name}"
        assert "–".encode() not in data, f"en dash in {path.name}"
