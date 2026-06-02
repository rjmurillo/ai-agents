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
    """Return titles of fence-aware top-level ``## `` headings.

    A line that toggles a fenced code block (``` or ~~~) flips fence state, and
    any ``## `` line while inside a fence is treated as content, not a heading.
    """
    titles: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith("## "):
            titles.append(line[3:].strip())
    return titles


def test_top_level_sections_skips_fenced_headings() -> None:
    text = (
        "## Real One\n"
        "```\n"
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
    missing = [title for title in sections if title not in audit_text]
    assert not missing, (
        f"{monolith.name} sections absent from the classification doc: {missing}"
    )


def test_audit_records_total_section_count() -> None:
    total = sum(
        len(top_level_sections(path.read_text(encoding="utf-8"))) for path in MONOLITHS
    )
    audit_text = ANALYSIS_DOC.read_text(encoding="utf-8")
    assert f"**{total}**" in audit_text, (
        f"audit total tally must state {total} sections"
    )
