"""Regression test for the Autonomy Guardrail citation in agent prompts.

The autonomy rule lives canonically in `AGENTS.md > Boundaries > Autonomy
Guardrail`. Each agent that participates in the guardrail (critic, implementer,
memory, orchestrator, qa, security) must carry a one-line citation pointing
back to AGENTS.md so the rule is visible at the prompt boundary.

This test pins that contract so a future template edit cannot silently drop
the citation. If a new agent joins the guardrail, add it to ``CITATION_AGENTS``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CITATION_AGENTS = (
    "critic",
    "implementer",
    "memory",
    "orchestrator",
    "qa",
    "security",
)

CITATION_PHRASE = "**Autonomy Guardrail**"
CITATION_TARGET = "`AGENTS.md`"

PLATFORM_PATHS = (
    ("templates/agents", "{name}.shared.md"),
    ("src/claude", "{name}.md"),
    ("src/copilot-cli", "{name}.agent.md"),
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
    """Each guardrail-participating agent prompt cites AGENTS.md once."""
    assert path.exists(), f"Expected agent prompt at {path}"
    text = path.read_text(encoding="utf-8")
    assert CITATION_PHRASE in text, (
        f"{path.relative_to(REPO_ROOT)} is missing the '{CITATION_PHRASE}' citation. "
        "Re-add the one-line pointer to AGENTS.md so the autonomy rule remains visible."
    )
    assert CITATION_TARGET in text, (
        f"{path.relative_to(REPO_ROOT)} cites the guardrail but does not reference "
        f"{CITATION_TARGET}. The citation must point back to the canonical rule."
    )


def test_agents_md_defines_autonomy_guardrail() -> None:
    """AGENTS.md is the system of record for the autonomy rule."""
    agents_md = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "**Autonomy Guardrail**" in agents_md, (
        "AGENTS.md must define the canonical 'Autonomy Guardrail' rule. "
        "Citations in agent prompts will dangle if it is removed or renamed."
    )


def test_no_dangling_principle_6_autonomy_citation() -> None:
    """Reject the prior 'Apply Principle 6' phrasing.

    `Principle 6` already names a different concept in
    `.agents/governance/agent-design-principles.md` (Consistent Interface).
    Conflating it with the autonomy rule confused readers; the rename is
    enforced here so it does not regress.
    """
    bad = "Apply Principle 6 from `AGENTS.md`"
    for path in _agent_files():
        text = path.read_text(encoding="utf-8")
        assert bad not in text, (
            f"{path.relative_to(REPO_ROOT)} still uses the old 'Apply Principle 6' "
            "phrasing. Rename to 'Apply the autonomy rule from `AGENTS.md`'."
        )
