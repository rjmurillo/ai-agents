"""Agent expertise weights for weighted consensus voting.

Defines relative expertise weights for different agents in various decision domains.
Higher weight indicates higher expertise in that domain.
"""

from __future__ import annotations

from typing import Literal

# Domain types for decision making
DecisionDomain = Literal[
    "architecture",
    "security",
    "implementation",
    "testing",
    "operations",
    "documentation",
    "breaking_change",
]

# Agent expertise weights by domain
# Scale: 0.5 (low expertise) to 2.0 (high expertise), default 1.0
AGENT_WEIGHTS: dict[DecisionDomain, dict[str, float]] = {
    "architecture": {
        "architect": 2.0,
        "independent-thinker": 1.5,
        "high-level-advisor": 1.5,
        "analyst": 1.2,
        "implementer": 1.0,
        "security": 1.2,
        "devops": 0.8,
        "qa": 0.8,
    },
    "security": {
        "security": 2.0,
        "architect": 1.5,
        "devops": 1.2,
        "implementer": 1.0,
        "analyst": 1.0,
        "qa": 0.8,
    },
    "implementation": {
        "implementer": 2.0,
        "analyst": 1.2,
        "qa": 1.2,
        "architect": 1.0,
        "devops": 1.0,
        "security": 1.0,
    },
    "testing": {
        "qa": 2.0,
        "implementer": 1.5,
        "security": 1.2,
        "analyst": 1.0,
        "architect": 0.8,
    },
    "operations": {
        "devops": 2.0,
        "security": 1.5,
        "implementer": 1.0,
        "architect": 1.0,
        "analyst": 0.8,
    },
    "documentation": {
        "explainer": 2.0,
        "analyst": 1.2,
        "architect": 1.0,
        "implementer": 1.0,
        "qa": 0.8,
    },
    "breaking_change": {
        "architect": 2.0,
        "high-level-advisor": 2.0,
        "security": 1.5,
        "implementer": 1.2,
        "qa": 1.2,
        "devops": 1.2,
    },
}


def get_agent_weight(agent: str, domain: DecisionDomain) -> float:
    """Get expertise weight for agent in specific domain.

    Args:
        agent: Agent name (e.g., "architect", "security")
        domain: Decision domain (e.g., "architecture", "security")

    Returns:
        Expertise weight (default 1.0 if not specified)
    """
    return AGENT_WEIGHTS.get(domain, {}).get(agent, 1.0)


def get_all_weights(domain: DecisionDomain) -> dict[str, float]:
    """Get all agent weights for a specific domain.

    Args:
        domain: Decision domain

    Returns:
        Dict mapping agent name to weight
    """
    return AGENT_WEIGHTS.get(domain, {})
