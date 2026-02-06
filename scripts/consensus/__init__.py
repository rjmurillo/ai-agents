"""Consensus mechanisms for multi-agent decision making.

This module provides consensus algorithms for handling disagreements between
specialist agents during impact analysis and complex decisions.

Supported algorithms:
- majority: Simple majority voting
- weighted: Expertise-weighted voting (agent type and domain)
- quorum: Require minimum participation before deciding
- unanimous: All specialists must agree

Reference: claude-flow's Consensus and Decision Making (wiki 8.4)
See: .agents/analysis/claude-flow-architecture-analysis.md
"""

from __future__ import annotations

from scripts.consensus.algorithms import (
    ConsensusAlgorithm,
    ConsensusResult,
    Vote,
    majority_consensus,
    quorum_consensus,
    unanimous_consensus,
    weighted_consensus,
)
from scripts.consensus.decision_recorder import DecisionRecorder
from scripts.consensus.weights import get_agent_weight, get_all_weights

__all__ = [
    "ConsensusAlgorithm",
    "ConsensusResult",
    "Vote",
    "majority_consensus",
    "quorum_consensus",
    "unanimous_consensus",
    "weighted_consensus",
    "DecisionRecorder",
    "get_agent_weight",
    "get_all_weights",
]
