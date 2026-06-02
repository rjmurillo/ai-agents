"""Regression test for the retirement of the `memory` agent (Issue #2102).

The `memory` agent duplicated the `memory` skill by name. Audit data showed
zero ``Task(subagent_type="memory")`` callers, slash references already routed
through ``Skill("memory")``, and 432 lines of agent guidance shadowing the
canonical skill body. Two artifacts named `memory` with different contracts is a
documented failure mode (Three-Artifact Distinction), so the agent was deleted
and its unique Serena-write guidance was absorbed into the skill.

This test pins that conversion so the agent cannot silently reappear and so the
absorbed guidance cannot silently drop out of the skill. It covers:

- positive: the `memory` skill still exists and carries the absorbed conventions
- negative: the `memory` agent source and every generated mirror are gone
- edge: no agent prompt re-introduces a ``subagent_type="memory"`` handoff

Refs Issue #2102 (conversion), Issue #2008 (regression guard).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Every tree where a `memory` agent prompt could live. The source of truth is
# templates/agents/<name>.shared.md; the rest are generated or committed mirrors.
AGENT_MEMORY_PATHS = (
    REPO_ROOT / "templates" / "agents" / "memory.shared.md",
    REPO_ROOT / ".claude" / "agents" / "memory.md",
    REPO_ROOT / "src" / "claude" / "memory.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "memory.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "memory.agent.md",
    REPO_ROOT / ".github" / "agents" / "memory.agent.md",
)

SKILL_PATH = REPO_ROOT / ".claude" / "skills" / "memory" / "SKILL.md"

# Load-bearing fragments absorbed from the retired agent into the skill.
ABSORBED_MARKERS = (
    "Serena Write Conventions",
    "Index-Table Insertion",
    "Source Tracking",
)

# Agent prompt directories scanned for a re-introduced memory subagent handoff.
AGENT_PROMPT_DIRS = (
    REPO_ROOT / "templates" / "agents",
    REPO_ROOT / ".claude" / "agents",
    REPO_ROOT / "src" / "claude",
)

_MEMORY_SUBAGENT_HANDOFF = re.compile(
    r"^subagent_type\s*:\s*['\"]?memory['\"]?\s*(?:#.*)?$",
    re.MULTILINE | re.IGNORECASE,
)


@pytest.mark.parametrize(
    "path", AGENT_MEMORY_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_memory_agent_file_absent(path: Path) -> None:
    """No `memory` agent prompt exists in any platform tree."""
    assert not path.exists(), (
        f"{path.relative_to(REPO_ROOT)} should not exist. The `memory` agent was "
        "retired in Issue #2102; its duties live in the `memory` skill. "
        "Do not re-add the agent."
    )


def test_memory_skill_present() -> None:
    """The `memory` skill remains the canonical artifact for memory operations."""
    assert SKILL_PATH.exists(), (
        f"Expected the memory skill at {SKILL_PATH.relative_to(REPO_ROOT)}. "
        "It is the single source of truth after the agent was retired."
    )


@pytest.mark.parametrize("marker", ABSORBED_MARKERS, ids=lambda m: m)
def test_skill_absorbed_agent_conventions(marker: str) -> None:
    """The skill carries the Serena-write guidance migrated from the agent."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert marker in text, (
        f"The memory skill must contain {marker!r}, absorbed from the retired "
        "memory agent (Issue #2102). If you intentionally moved this guidance "
        "elsewhere, update ABSORBED_MARKERS and cite where it now lives."
    )


def test_no_agent_prompt_reintroduces_memory_subagent() -> None:
    """No agent prompt re-introduces a ``subagent_type="memory"`` handoff."""
    offenders: list[str] = []
    for prompt_dir in AGENT_PROMPT_DIRS:
        if not prompt_dir.is_dir():
            continue
        for path in sorted(prompt_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if _MEMORY_SUBAGENT_HANDOFF.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "These agent prompts reference a retired `memory` subagent via "
        f"subagent_type=\"memory\": {offenders}. Route memory work through "
        "Skill(\"memory\") instead (Issue #2102)."
    )
