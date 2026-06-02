#!/usr/bin/env python3
"""Shared quality gate agent metadata for workflow consumer scripts."""

from __future__ import annotations

QUALITY_GATE_AGENTS = (
    "security",
    "qa",
    "analyst",
    "architect",
    "devops",
    "roadmap",
    "reliability",
    "observability",
    "agent-safety",
    "decision-rigor",
)

QUALITY_GATE_AGENT_DISPLAY_NAMES = {
    "security": "Security",
    "qa": "QA",
    "analyst": "Analyst",
    "architect": "Architect",
    "devops": "DevOps",
    "roadmap": "Roadmap",
    "reliability": "Reliability",
    "observability": "Observability",
    "agent-safety": "Agent Safety",
    "decision-rigor": "Decision Rigor",
}


def agent_env_name(agent: str) -> str:
    """Return the environment variable prefix for an agent name."""
    return agent.upper().replace("-", "_")


def agent_arg_name(agent: str) -> str:
    """Return the argparse destination prefix for an agent name."""
    return agent.replace("-", "_")
