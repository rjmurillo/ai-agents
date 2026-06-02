"""Audit-completeness checks for issue #1769 Phase 1.

The classification document at
``.agents/analysis/1769-monolith-section-classification.md`` maps every
top-level ``##`` section in the three always-loaded monolith instruction files
to a destination. These tests pin the audit's core invariant: no monolith
section is silently dropped from the classification.

The failure mode this guards against: a future edit adds a new ``##`` section
to a monolith, and a stale audit no longer covers it. The test fails until the
audit is updated.

Headings inside fenced code blocks are template or example content, not real
sections, so ``top_level_sections`` skips them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DOC = (
    PROJECT_ROOT / ".agents" / "analysis" / "1769-monolith-section-classification.md"
)
MONOLITHS = (
    PROJECT_ROOT / ".agents" / "AGENT-SYSTEM.md",
    PROJECT_ROOT / ".agents" / "AGENT-INSTRUCTIONS.md",
    PROJECT_ROOT / ".agents" / "SESSION-PROTOCOL.md",
)


def top_level_sections(text: str) -> list[str]:
    """Return titles of fence-aware top-level ``## `` headings."""
    titles: list[str] = []
    active_fence: tuple[str, int] | None = None
    for line in text.split("\n"):
        stripped = line.strip()
        if active_fence is None and stripped.startswith(("```", "~~~")):
            marker = stripped[0]
            active_fence = (marker, len(stripped) - len(stripped.lstrip(marker)))
            continue
        if active_fence is not None:
            marker, minimum_length = active_fence
            if stripped.startswith(marker * minimum_length) and set(stripped) == {marker}:
                active_fence = None
            continue
        if line.startswith("## "):
            titles.append(line[3:].strip())
    return titles


def audit_mentions_section(audit_text: str, monolith_name: str, title: str) -> bool:
    """Return whether a section title appears in the monolith's table block."""
    monolith_heading = f"## {monolith_name}"
    next_monolith_heading = r"\n## [A-Z][A-Z-]+\.md"
    block_match = re.search(
        rf"^{re.escape(monolith_heading)}.*?(?={next_monolith_heading}|\Z)",
        audit_text,
        flags=re.M | re.S,
    )
    if block_match is None:
        return False
    title_cell = re.escape(title)
    title_pattern = rf"^\|\s*(?:\d+\.\s*)?{title_cell}\s*\|"
    return re.search(title_pattern, block_match[0], re.M) is not None


def test_top_level_sections_skips_fenced_headings() -> None:
    text = (
        "## Real One\n"
        "~~~\n"
        "```\n"
        "## Fenced Not A Section\n"
        "```\n"
        "~~~\n"
        "## Real Two\n"
    )
    assert top_level_sections(text) == ["Real One", "Real Two"]


def test_top_level_sections_requires_bare_closing_fence() -> None:
    text = (
        "## Real One\n"
        "```\n"
        "```text\n"
        "## Fenced Not A Section\n"
        "```\n"
        "## Real Two\n"
    )
    assert top_level_sections(text) == ["Real One", "Real Two"]


def test_top_level_sections_ignores_deeper_headings() -> None:
    text = "## Top\n### Sub\n#### Deeper\n## Top Two\n"
    assert top_level_sections(text) == ["Top", "Top Two"]


def test_top_level_sections_empty_when_no_headings() -> None:
    assert top_level_sections("no headings here\njust prose\n") == []


def test_analysis_doc_exists() -> None:
    assert ANALYSIS_DOC.is_file(), f"missing audit doc: {ANALYSIS_DOC}"


@pytest.mark.parametrize("monolith", MONOLITHS, ids=lambda p: p.name)
def test_every_monolith_section_is_classified(monolith: Path) -> None:
    assert monolith.is_file(), f"missing monolith: {monolith}"
    audit_text = ANALYSIS_DOC.read_text(encoding="utf-8")
    sections = top_level_sections(monolith.read_text(encoding="utf-8"))
    assert sections, f"no top-level sections found in {monolith.name}"
    missing = [
        title
        for title in sections
        if not audit_mentions_section(audit_text, monolith.name, title)
    ]
    assert not missing, (
        f"{monolith.name} sections absent from the classification doc: {missing}"
    )


def test_audit_records_total_section_count() -> None:
    total = sum(
        len(top_level_sections(path.read_text(encoding="utf-8"))) for path in MONOLITHS
    )
    audit_text = ANALYSIS_DOC.read_text(encoding="utf-8")
    total_row = rf"^\|\s*\*\*Total\*\*\s*\|\s*\*\*{total}\*\*\s*\|"
    assert re.search(total_row, audit_text, re.M), (
        f"audit total tally must state {total} sections"
    )
