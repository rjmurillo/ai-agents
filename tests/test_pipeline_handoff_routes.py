"""Pipeline handoff routes name registered agents (REQ-029 AC1, AC2).

Issue #5393 asked for a check that the analyst, planner, critic, implementer,
and QA roles hand off to agents that exist. A route naming a retired or never
registered agent fails silently: the delegation resolves to nothing and the
step is skipped. The critic's handoff routed ``NEEDS_REVISION`` to ``planner``,
a name no agent file carries, until this test pinned it.

Two claims, each graded on the canonical template and the binplaced Claude
copy so a template edit that does not reach the install fails here:

* the critic's ``## Handoff`` verdict routes name registered agents or the
  orchestrator (AC2);
* the critic's ``## Handoff`` names every verdict its Verdict Rules table
  defines, so a verdict the critic can emit always has a next step (AC2);
* the orchestrator's Routing Algorithm lifecycle chain names registered agents,
  places ``critic`` before ``implementer``, and keeps the readiness review
  after ``qa`` (AC1).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_TEMPLATES = REPO_ROOT / "templates" / "agents"

CRITIC_PATHS = (
    Path("templates/agents/critic.shared.md"),
    Path(".claude/agents/critic.md"),
)
ORCHESTRATOR_PATHS = (
    Path("templates/agents/orchestrator.shared.md"),
    Path(".claude/agents/orchestrator.md"),
)

_ROUTE = re.compile(r"(?:→|->)\s*(?:return to |escalate to )?([a-z][a-z-]+)")
_VERDICT_ROW = re.compile(r"^\| \*\*([A-Z_]+)\*\* \|", re.MULTILINE)
_CHAIN = re.compile(r"sequential routing:\s*(.+)")


def registered_agents() -> set[str]:
    """Agent names that own a shared template, plus the coordinator itself."""
    names = {p.name.removesuffix(".shared.md") for p in AGENT_TEMPLATES.glob("*.shared.md")}
    return names | {"orchestrator"}


def handoff_section(text: str) -> str:
    """Return the body of the last ``## Handoff`` section."""
    parts = re.split(r"^## Handoff\s*$", text, flags=re.MULTILINE)
    assert len(parts) > 1, "no '## Handoff' section"
    body = parts[-1]
    return re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]


def chain_names(line: str) -> list[str]:
    """Split an arrow chain into bare names, dropping parentheticals."""
    names = []
    for step in re.split(r"→|->", line):
        token = step.strip().split(" ")[0].split("(")[0].strip()
        if token:
            names.append(token)
    return names


@pytest.mark.parametrize("path", CRITIC_PATHS, ids=str)
def test_critic_verdict_routes_name_registered_agents(path: Path) -> None:
    """REQ-029 AC2: every critic handoff route resolves to an agent file."""
    section = handoff_section((REPO_ROOT / path).read_text(encoding="utf-8"))
    routes = _ROUTE.findall(section)
    assert routes, f"{path}: no verdict routes found in Handoff"
    unknown = sorted(set(routes) - registered_agents())
    assert not unknown, f"{path}: handoff routes to unregistered agents {unknown}"


@pytest.mark.parametrize("path", CRITIC_PATHS, ids=str)
def test_critic_handoff_routes_every_verdict_it_can_emit(path: Path) -> None:
    """REQ-029 AC2: each verdict in the Verdict Rules table has a handoff route."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    verdicts = set(_VERDICT_ROW.findall(text))
    assert verdicts >= {"APPROVED", "APPROVED_WITH_CONCERNS", "NEEDS_REVISION", "BLOCKED"}, verdicts
    section = handoff_section(text)
    missing = sorted(v for v in verdicts if v not in section)
    assert not missing, f"{path}: Handoff names no route for {missing}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_orchestrator_lifecycle_chain_gates_implementer_behind_critic(path: Path) -> None:
    """REQ-029 AC1: the lifecycle chain names real agents and runs critic before implementer."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    match = _CHAIN.search(text)
    assert match, f"{path}: no 'sequential routing:' chain"
    names = chain_names(match.group(1))
    agents = [n for n in names if not n.startswith("/")]
    unknown = sorted(set(agents) - registered_agents())
    assert not unknown, f"{path}: chain names unregistered agents {unknown}"
    assert "critic" in agents and "implementer" in agents, f"{path}: chain is {names}"
    assert agents.index("critic") < agents.index("implementer"), (
        f"{path}: critic must gate implementer, chain is {names}"
    )
    assert "qa" in agents and agents[-1] == "critic" and agents.index("qa") < len(agents) - 1, (
        f"{path}: readiness review must follow qa, chain is {names}"
    )
