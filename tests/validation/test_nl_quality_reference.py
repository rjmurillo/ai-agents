"""Doctrine checks for the executable natural-language artifact reference (#5397).

The ladder and the quality mapping are review doctrine, not script logic. What a
test can prove mechanically: the canonical reference holds each required
element, consumers point to it, and no consumer copies the model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_REF_REL = ".claude/skills/code-qualities-assessment/references/executable-nl-artifacts.md"
_REF = " ".join((_ROOT / _REF_REL).read_text(encoding="utf-8").split())
_CONSUMERS = (
    "templates/skills/review.SKILL.md.tmpl",
    "templates/skills/doc-accuracy.SKILL.md.tmpl",
    "templates/agents/quality-auditor.shared.md",
    "templates/agents/partials/quality-auditor-intro.mustache",
)
_COPIED_HEADINGS = (
    "## Minimal-implementation ladder",
    "## Quality mapping",
    "## Change amplification",
)


def test_ladder_rungs_appear_in_order() -> None:
    markers = [
        "Does this need to exist?",
        "already have it",
        "standard library",
        "native platform",
        "installed dependency",
        "no new abstraction",
        "minimum new abstraction",
    ]
    positions = [_REF.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_ladder_keeps_mandatory_safety_behavior() -> None:
    for word in (
        "validation",
        "error handling",
        "security",
        "accessibility",
        "reliability",
        "observability",
    ):
        assert word in _REF
    assert "negligent omission" in _REF


@pytest.mark.parametrize(
    "needle",
    [
        "reject the new copy",
        "reject the custom implementation",
        "remove it or simplify",
    ],
)
def test_review_checklist_rejects_each_ladder_violation(needle: str) -> None:
    assert needle in _REF


@pytest.mark.parametrize(
    "needle",
    [
        "one authored source -> N generated projections",
        "Removes a representation",
        "steady",
        "exactly three replicas",
    ],
)
def test_reference_holds_model_elements(needle: str) -> None:
    assert needle.lower() in _REF.lower() or needle in _REF


def test_reference_has_no_dash_or_banned_words() -> None:
    assert "—" not in _REF
    assert "–" not in _REF
    for word in ("robust", "comprehensive", "fundamental", "significant", "crucial"):
        assert word not in _REF.lower()


@pytest.mark.parametrize("rel", _CONSUMERS)
def test_consumer_points_to_reference_without_copying_it(rel: str) -> None:
    text = (_ROOT / rel).read_text(encoding="utf-8")
    assert "executable-nl-artifacts.md" in text
    assert not any(heading in text for heading in _COPIED_HEADINGS)


def test_skill_template_owns_the_capability_and_links_the_reference() -> None:
    text = (_ROOT / "templates/skills/code-qualities-assessment.SKILL.md.tmpl").read_text(
        encoding="utf-8"
    )
    assert "- artifact-neutral-code-quality" in text
    assert "references/executable-nl-artifacts.md" in text
    assert "behavior-driving Markdown" in text


def test_no_parallel_quality_skill_exists() -> None:
    names = {p.name for p in (_ROOT / "templates/skills").glob("*.SKILL.md.tmpl")}
    assert not {"prompt-quality.SKILL.md.tmpl", "minimal-code.SKILL.md.tmpl"} & names
