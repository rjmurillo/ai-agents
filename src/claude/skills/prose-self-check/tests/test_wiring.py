"""Wiring tests for the prose-self-check skill (issue #2931).

The skill only pays off when the prose-emitting agents and the spec-generator
skill actually point at it. These tests pin that wiring: each canonical source
that emits user-facing prose must reference the prose-self-check skill by its
slug, so a future edit that drops the pointer fails here instead of shipping a
silently-unwired agent.

Scope is the canonical sources only (templates/agents/*.shared.md and the
spec-generator SKILL.md). The generated and hand-maintained sibling copies are
guarded for co-change by scripts/validation/validate_install_parity.py and for
body parity by build/scripts/detect_agent_drift.py; re-asserting them here would
duplicate those gates.

Tests follow Arrange/Act/Assert, one behavior per test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_SLUG = "prose-self-check"

_DOT = "."
_CLAUDE_DIR_NAME = _DOT + "claude"
_SKILLS_DIR_NAME = "skills"
_TEMPLATES_SEGMENTS = ("templates", "agents")
_SPEC_GENERATOR_SEGMENTS = (_CLAUDE_DIR_NAME, _SKILLS_DIR_NAME, "spec-generator", "SKILL.md")

_PROSE_AGENTS = ("analyst", "explainer", "pr-comment-responder", "retrospective")


def _find_repo_root(start: Path) -> Path | None:
    """Walk up until a directory holds both the templates and canonical skill trees."""
    for parent in [start, *start.parents]:
        templates = parent.joinpath(*_TEMPLATES_SEGMENTS)
        canonical = parent / _CLAUDE_DIR_NAME / _SKILLS_DIR_NAME
        if templates.is_dir() and canonical.is_dir():
            return parent
    return None


REPO_ROOT = _find_repo_root(Path(__file__).resolve())


def _canonical_prose_sources() -> list[Path]:
    """Every canonical source that must reference the prose-self-check skill."""
    if REPO_ROOT is None:
        return []
    sources = [
        REPO_ROOT.joinpath(*_TEMPLATES_SEGMENTS, f"{name}.shared.md")
        for name in _PROSE_AGENTS
    ]
    sources.append(REPO_ROOT.joinpath(*_SPEC_GENERATOR_SEGMENTS))
    return sources


def test_repo_root_resolves() -> None:
    """The marker walk must find the repo root, or every other test is a no-op."""
    assert (
        REPO_ROOT is not None
    ), "could not resolve repo root from templates and canonical skill trees"


@pytest.mark.parametrize("source", _canonical_prose_sources(), ids=lambda p: p.name)
def test_source_exists(source: Path) -> None:
    """Each expected canonical source is present on disk."""
    assert source.is_file(), f"missing canonical prose source: {source}"


@pytest.mark.parametrize("source", _canonical_prose_sources(), ids=lambda p: p.name)
def test_source_references_prose_self_check(source: Path) -> None:
    """Each canonical prose source wires in the prose-self-check skill by slug."""
    text = source.read_text(encoding="utf-8")
    assert _SKILL_SLUG in text, (
        f"{source} does not reference the {_SKILL_SLUG!r} skill; "
        "the prose self-check pointer was dropped"
    )


@pytest.mark.parametrize("name", _PROSE_AGENTS)
def test_prose_agent_has_self_check_heading(name: str) -> None:
    """Each prose-emitting agent template carries a Prose Self-Check heading."""
    if REPO_ROOT is None:
        pytest.skip("repo root unresolved")
    template = REPO_ROOT.joinpath(*_TEMPLATES_SEGMENTS, f"{name}.shared.md")
    text = template.read_text(encoding="utf-8")
    assert "## Prose Self-Check" in text, f"{template} lost its Prose Self-Check section"


def test_all_prose_agents_covered() -> None:
    """Negative control: the covered set is exactly the four prose-emitting agents."""
    assert set(_PROSE_AGENTS) == {"analyst", "explainer", "pr-comment-responder", "retrospective"}
