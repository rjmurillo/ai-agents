"""Tests for the Table C net-new wiki concept imports (issue #1937).

Validates the five vendor-safe reference files imported from the user's local
wiki and their citations from the canonical review-axis files.

Acceptance criteria covered:

- AC1: each reference cites its original wiki path in frontmatter (`source:`)
  and inlines the concept body (no external links to project-only paths).
- AC2: each canonical axis file cites the new reference via a vendor-safe
  `.claude/` path.
- AC3: no `.agents/`, `.serena/`, `.github/`, or `/Documents/` path appears in
  the body or links of any imported reference.
- AC4: each reference has a "Why this lens applies in PR review" section.

Spec: issue #1937 (Child 4 of epic #1933).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# AC3 forbidden path fragments: project-only or user-local, not vendor-safe.
FORBIDDEN_PATH_FRAGMENTS: tuple[str, ...] = (
    ".agents/",
    ".serena/",
    ".github/",
    "/Documents/",
)

# Imported reference file -> wiki source path recorded in frontmatter.
IMPORTED_REFERENCES: dict[str, str] = {
    ".claude/skills/decision-critic/references/decision-pre-committed-metrics.md": (
        "wiki/concepts/Decision Making/Pre-Committed Metrics Force Honest Evaluation.md"
    ),
    ".claude/skills/security-scan/references/agent-memory-inference-leakage.md": (
        "wiki/concepts/AI Safety/Agent Unauthorized Memory Inference.md"
    ),
    ".claude/skills/security-scan/references/agent-guardrails-template.md": (
        "wiki/concepts/AI Safety/Agent Guardrails Template.md"
    ),
    ".claude/skills/observability/references/otel-semantic-conventions.md": (
        "wiki/concepts/Observability/OTel Semantic Conventions.md"
    ),
    ".claude/skills/observability/references/distributed-systems-fallacies.md": (
        "wiki/concepts/Architectural Patterns/8 Fallacies of Distributed Computing.md"
    ),
}

# Canonical axis file -> reference paths it must cite (AC2).
AXIS_CITATIONS: dict[str, tuple[str, ...]] = {
    ".claude/skills/review/references/architect.md": (
        ".claude/skills/observability/references/distributed-systems-fallacies.md",
    ),
    ".claude/skills/review/references/reliability.md": (
        ".claude/skills/observability/references/distributed-systems-fallacies.md",
    ),
    ".claude/skills/review/references/decision-rigor.md": (
        ".claude/skills/decision-critic/references/decision-pre-committed-metrics.md",
    ),
    ".claude/skills/review/references/agent-safety.md": (
        ".claude/skills/security-scan/references/agent-guardrails-template.md",
        ".claude/skills/security-scan/references/agent-memory-inference-leakage.md",
    ),
    ".claude/skills/review/references/observability.md": (
        ".claude/skills/observability/references/otel-semantic-conventions.md",
    ),
}

LENS_HEADING = "## Why This Lens Applies In PR Review"

REQUIRED_REFERENCE_SECTIONS: dict[str, tuple[str, ...]] = {
    ".claude/skills/decision-critic/references/decision-pre-committed-metrics.md": (
        "# Pre-Committed Metrics Force Honest Evaluation",
        "## Principle",
        "## The Three Instantiations",
        "## Operating Consequences",
        LENS_HEADING,
        "## Source",
    ),
    ".claude/skills/security-scan/references/agent-memory-inference-leakage.md": (
        "# Agent Unauthorized Memory Inference",
        "## Principle",
        "## The Audited Failure",
        "## The Permission Distinction",
        LENS_HEADING,
        "## Source",
    ),
    ".claude/skills/security-scan/references/agent-guardrails-template.md": (
        "# Agent Guardrails Template",
        "## Principle",
        "## The Four Laws Of Agent Safety",
        "## How To Apply",
        LENS_HEADING,
        "## Source",
    ),
    ".claude/skills/observability/references/otel-semantic-conventions.md": (
        "# OTel Semantic Conventions",
        "## Principle",
        "## What They Solve",
        "## Attribute Namespaces",
        LENS_HEADING,
        "## Source",
    ),
    ".claude/skills/observability/references/distributed-systems-fallacies.md": (
        "# 8 Fallacies of Distributed Computing",
        "## Principle",
        "## The Fallacies",
        "## Mitigations",
        LENS_HEADING,
        "## Source",
    ),
}


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    if end == -1:
        return ""
    return text[4:end]


@pytest.mark.parametrize("rel_path", sorted(IMPORTED_REFERENCES))
def test_imported_reference_file_exists(rel_path: str) -> None:
    assert (REPO_ROOT / rel_path).is_file(), f"missing imported reference: {rel_path}"


@pytest.mark.parametrize(
    ("rel_path", "wiki_source"), sorted(IMPORTED_REFERENCES.items())
)
def test_reference_cites_wiki_source_in_frontmatter(
    rel_path: str, wiki_source: str
) -> None:
    """AC1: frontmatter records the original wiki path as attribution."""
    frontmatter = _frontmatter(_read(rel_path))
    assert f"source: {wiki_source}" in frontmatter, (
        f"{rel_path} frontmatter must cite wiki source `{wiki_source}`"
    )


@pytest.mark.parametrize("rel_path", sorted(IMPORTED_REFERENCES))
def test_reference_has_lens_section(rel_path: str) -> None:
    """AC4: each reference explains why the lens applies in PR review."""
    assert LENS_HEADING in _read(rel_path), (
        f"{rel_path} must contain a `{LENS_HEADING}` section"
    )


@pytest.mark.parametrize(
    ("rel_path", "required_sections"), sorted(REQUIRED_REFERENCE_SECTIONS.items())
)
def test_reference_inlines_body(
    rel_path: str, required_sections: tuple[str, ...]
) -> None:
    """AC1: the concept body is inlined with its core structural sections."""
    body = _read(rel_path)
    missing = [section for section in required_sections if section not in body]
    assert not missing, f"{rel_path} missing inlined concept sections: {missing}"


@pytest.mark.parametrize("rel_path", sorted(IMPORTED_REFERENCES))
def test_reference_is_vendor_safe(rel_path: str) -> None:
    """AC3: no project-only or user-local path appears in the file.

    The `source:` frontmatter records `wiki/concepts/...`, which contains none
    of the forbidden fragments, so attribution does not trip this check.
    """
    text = _read(rel_path)
    found = [frag for frag in FORBIDDEN_PATH_FRAGMENTS if frag in text]
    assert not found, f"{rel_path} contains vendor-unsafe path fragments: {found}"


def test_no_wiki_filesystem_link_in_references() -> None:
    """AC1/AC3: bodies must not link back to the user's local wiki on disk."""
    for rel_path in IMPORTED_REFERENCES:
        text = _read(rel_path)
        assert "~/Documents" not in text, f"{rel_path} links to the local wiki path"
        assert "Mobile/wiki" not in text, f"{rel_path} links to the local wiki path"


@pytest.mark.parametrize(
    ("axis_path", "expected_citations"), sorted(AXIS_CITATIONS.items())
)
def test_axis_cites_new_reference(
    axis_path: str, expected_citations: tuple[str, ...]
) -> None:
    """AC2: the axis file cites each new reference via its vendor-safe path."""
    text = _read(axis_path)
    for citation in expected_citations:
        assert citation in text, f"{axis_path} must cite `{citation}`"


def test_distributed_fallacies_cited_by_two_axes() -> None:
    """Edge: the 8 Fallacies reference serves both architect and reliability."""
    citing_axes = [
        axis
        for axis, refs in AXIS_CITATIONS.items()
        if ".claude/skills/observability/references/distributed-systems-fallacies.md"
        in refs
    ]
    assert set(citing_axes) == {
        ".claude/skills/review/references/architect.md",
        ".claude/skills/review/references/reliability.md",
    }
