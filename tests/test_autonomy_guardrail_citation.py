"""Regression test for the Autonomy Guardrail citation in agent prompts.

The autonomy rule lives canonically in `AGENTS.md > Boundaries > Autonomy
Guardrail`. Each agent that participates in the guardrail (critic, implementer,
orchestrator, qa, security) must carry a one-line citation pointing
back to AGENTS.md so the rule is visible at the prompt boundary.

This test pins that contract so a future template edit cannot silently drop
the citation. If a new agent joins the guardrail, add it to ``CITATION_AGENTS``;
when an agent is retired, remove it. The `memory` agent was retired in Issue
#2102 (its skill-shaped duties moved to the `memory` skill), so it no longer
appears here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CITATION_AGENTS = (
    "critic",
    "implementer",
    "orchestrator",
    "qa",
    "security",
)

CITATION_PHRASE = "**Autonomy Guardrail**"
CITATION_TARGET = "`AGENTS.md`"

PLATFORM_PATHS = (
    ("templates/agents", "{name}.shared.md"),
    ("src/claude", "{name}.md"),
    ("src/copilot-cli/agents", "{name}.agent.md"),
    ("src/vs-code-agents", "{name}.agent.md"),
)


def _agent_files() -> list[Path]:
    paths: list[Path] = []
    for subdir, pattern in PLATFORM_PATHS:
        for name in CITATION_AGENTS:
            paths.append(REPO_ROOT / subdir / pattern.format(name=name))
    return paths


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_agent_carries_autonomy_guardrail_citation(path: Path) -> None:
    """Each guardrail-participating agent prompt carries the citation exactly once.

    The substring checks that came before this version passed even when the
    citation appeared zero times on the same line as the AGENTS.md reference,
    or when it appeared more than once. We assert exactly one line that
    contains both tokens together so a stray duplicate or a split-across-lines
    citation is caught.
    """
    assert path.exists(), f"Expected agent prompt at {path}"
    text = path.read_text(encoding="utf-8")
    citation_lines = [
        line
        for line in text.splitlines()
        if CITATION_PHRASE in line and CITATION_TARGET in line
    ]
    assert len(citation_lines) == 1, (
        f"{path.relative_to(REPO_ROOT)} must contain exactly one one-line autonomy "
        f"guardrail citation with both {CITATION_PHRASE!r} and {CITATION_TARGET!r}. "
        f"Found {len(citation_lines)}. Re-add or deduplicate the one-line pointer "
        "to AGENTS.md so the autonomy rule remains visible without drift."
    )


def test_agents_md_defines_autonomy_guardrail() -> None:
    """AGENTS.md is the system of record for the autonomy rule."""
    agents_md = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "**Autonomy Guardrail**" in agents_md, (
        "AGENTS.md must define the canonical 'Autonomy Guardrail' rule. "
        "Citations in agent prompts will dangle if it is removed or renamed."
    )


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_dangling_principle_6_autonomy_citation(path: Path) -> None:
    """Reject any 'Principle 6' or 'Principle #6' phrasing.

    `Principle 6` already names a different concept in
    `.agents/governance/agent-design-principles.md` (Consistent Interface).
    Conflating it with the autonomy rule confused readers; the rename is
    enforced here so it does not regress.
    """
    bad_patterns = ("Principle 6", "Principle #6")
    text = path.read_text(encoding="utf-8")
    for bad in bad_patterns:
        assert bad not in text, (
            f"{path.relative_to(REPO_ROOT)} still uses '{bad}' phrasing. "
            "Use 'Autonomy Guardrail' instead to avoid conflation with "
            "agent-design-principles.md Principle 6 (Consistent Interface)."
        )
