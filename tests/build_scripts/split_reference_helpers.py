"""Shared constants and helpers for the split-agent reference-root tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

from generate_agents_common import (  # noqa: E402
    CHECKOUT_CLAUSE,
    CLAUDE_ROOT,
    COPILOT_ROOT,
)

HOST_ROOTS = (CLAUDE_ROOT, COPILOT_ROOT)


FALLBACK_TREES = ("src/muse/agents", "src/codex/agents")


CURSOR_TREE = "src/cursor/agents"


def ref(root: str, skill: str) -> str:
    return f"{root}/skills/{skill}/references/"


def sentence(root: str, skill: str) -> str:
    return f"References live under `{ref(root, skill)}`. They serve this agent."


def rendered_sentence(root: str, skill: str) -> str:
    clause = CHECKOUT_CLAUSE.format(skill=skill)
    return f"References live under `{ref(root, skill)}`.{clause} They serve this agent."


def split_agent_files(tree: str) -> list[Path]:
    files = sorted((REPO_ROOT / tree).glob("*.*"))
    assert files, f"no agent files under {tree}"
    return files


SPLIT_AGENTS = ("architect", "critic", "implementer", "orchestrator", "qa", "security")


def skills_with_references() -> list[str]:
    root = REPO_ROOT / "src" / "claude" / "skills"
    return sorted(p.parent.name for p in root.glob("*/references") if p.is_dir())


AGENT_SKILL = {
    "architect": "adr-review",
    "critic": "decision-critic",
    "implementer": "build",
    "orchestrator": "autoplan",
    "qa": "test",
    "security": "security-scan",
}


MARKER = "<!-- vendor-portability: declares `.agents/` paths. -->"
