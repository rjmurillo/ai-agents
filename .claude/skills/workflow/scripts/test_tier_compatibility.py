#!/usr/bin/env python3
"""Validate agent sequences respect tier hierarchy rules.

Checks that agent sequences follow valid delegation patterns:
- Higher tiers can delegate to lower tiers
- Same tier agents can execute in parallel
- Lower tiers cannot delegate to higher tiers (must escalate)

Tier hierarchy (1 = highest authority):
- Tier 1: Expert (high-level-advisor, independent-thinker, architect, roadmap)
- Tier 2: Manager (orchestrator, milestone-planner, critic, etc.)
- Tier 3: Builder (implementer, qa, devops, security, debug)
- Tier 4: Integration (analyst, explainer, task-decomposer, retrospective, spec-generator, etc.)

Exit codes:
    0: Validation passed
    1: Tier violation detected
    2: Configuration error (invalid agent name)
    3: Parameter validation error

See .agents/AGENT-SYSTEM.md Section 2.5 for tier hierarchy documentation.
Related: orchestrator-routing-algorithm.md Phase 2.5
ADR Reference: ADR-009 (Parallel-Safe Multi-Agent Design)
"""

from __future__ import annotations

import argparse
import sys

TIER_HIERARCHY: dict[str, int] = {
    "expert": 1,
    "manager": 2,
    "builder": 3,
    "integration": 4,
}

AGENT_TIERS: dict[str, str] = {
    # Expert Tier (1)
    "high-level-advisor": "expert",
    "independent-thinker": "expert",
    "architect": "expert",
    "roadmap": "expert",
    # Manager Tier (2)
    "orchestrator": "manager",
    "milestone-planner": "manager",
    "critic": "manager",
    "issue-feature-review": "manager",
    "pr-comment-responder": "manager",
    # Builder Tier (3)
    "implementer": "builder",
    "qa": "builder",
    "devops": "builder",
    "security": "builder",
    "debug": "builder",
    # Integration Tier (4)
    "analyst": "integration",
    "explainer": "integration",
    "task-decomposer": "integration",
    "retrospective": "integration",
    "spec-generator": "integration",
    "adr-generator": "integration",
    "backlog-generator": "integration",
    "janitor": "integration",
    "memory": "integration",
    "skillbook": "integration",
    "context-retrieval": "integration",
}


def validate_sequence(agent_sequence: list[str]) -> list[dict]:
    """Validate an agent sequence for tier hierarchy violations.

    Returns a list of violation dicts. Empty list means valid.
    """
    # Validate all agents are known
    for agent in agent_sequence:
        if agent not in AGENT_TIERS:
            valid_agents = ", ".join(sorted(AGENT_TIERS.keys()))
            print(
                f"Unknown agent: '{agent}'. Valid agents: {valid_agents}",
                file=sys.stderr,
            )
            sys.exit(2)

    violations = []

    for i in range(1, len(agent_sequence)):
        current_agent = agent_sequence[i]
        current_tier = AGENT_TIERS[current_agent]
        current_level = TIER_HIERARCHY[current_tier]

        previous_agent = agent_sequence[i - 1]
        previous_tier = AGENT_TIERS[previous_agent]
        previous_level = TIER_HIERARCHY[previous_tier]

        if current_level >= previous_level:
            # Same tier (parallel) or delegation to lower tier: valid
            continue

        # Lower tier trying to delegate to higher tier: invalid
        violations.append(
            {
                "position": i,
                "agent": current_agent,
                "tier": current_tier,
                "level": current_level,
                "previous_agent": previous_agent,
                "previous_tier": previous_tier,
                "previous_level": previous_level,
                "message": (
                    f"Invalid delegation: {previous_agent} ({previous_tier}) "
                    f"cannot delegate to {current_agent} ({current_tier}). "
                    f"Use escalation instead."
                ),
            }
        )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate agent sequence respects tier hierarchy rules."
    )
    parser.add_argument(
        "agents",
        nargs="+",
        help="Agent names in execution order",
    )
    args = parser.parse_args()

    if not args.agents:
        print("Error: at least one agent name required", file=sys.stderr)
        return 3

    violations = validate_sequence(args.agents)

    if violations:
        print("Tier Validation: FAILED")
        print(f"Found {len(violations)} violation(s):\n")
        for v in violations:
            print(f"  Position {v['position']}: {v['message']}")
        return 1

    print("Tier Validation: PASSED")
    print(f"Agent sequence: {' -> '.join(args.agents)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
