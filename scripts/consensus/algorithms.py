"""Consensus algorithm implementations.

Provides various consensus mechanisms for multi-agent decision making:
- Majority: Simple majority voting
- Weighted: Expertise-based weighted voting
- Quorum: Require minimum participation threshold
- Unanimous: All agents must agree
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class ConsensusAlgorithm(StrEnum):
    """Supported consensus algorithms."""

    MAJORITY = "majority"
    WEIGHTED = "weighted"
    QUORUM = "quorum"
    UNANIMOUS = "unanimous"


@dataclass
class Vote:
    """Individual agent vote with rationale.

    Attributes:
        agent: Agent name (e.g., "architect", "security", "implementer")
        position: Vote position (approve, reject, abstain)
        rationale: Explanation for the vote
        confidence: Confidence score 0.0-1.0
    """

    agent: str
    position: Literal["approve", "reject", "abstain"]
    rationale: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Validate confidence score."""
        if not 0.0 <= self.confidence <= 1.0:
            msg = f"Confidence must be 0.0-1.0, got {self.confidence}"
            raise ValueError(msg)


@dataclass
class ConsensusResult:
    """Result of consensus evaluation.

    Attributes:
        decision: Final decision (approved, rejected, no_consensus)
        algorithm: Algorithm used to reach decision
        confidence_score: Overall confidence in the decision (0.0-1.0)
        votes_for: Count of approval votes
        votes_against: Count of rejection votes
        abstentions: Count of abstentions
        summary: Human-readable summary of the decision
    """

    decision: Literal["approved", "rejected", "no_consensus"]
    algorithm: ConsensusAlgorithm
    confidence_score: float
    votes_for: int
    votes_against: int
    abstentions: int
    summary: str


def majority_consensus(votes: list[Vote]) -> ConsensusResult:
    """Simple majority voting.

    Decision requires more approvals than rejections.
    Abstentions are not counted toward the majority.

    Args:
        votes: List of agent votes

    Returns:
        ConsensusResult with decision based on simple majority
    """
    approvals = [v for v in votes if v.position == "approve"]
    rejections = [v for v in votes if v.position == "reject"]
    abstentions = [v for v in votes if v.position == "abstain"]

    votes_for = len(approvals)
    votes_against = len(rejections)
    abstain_count = len(abstentions)

    # Calculate weighted confidence from approvers or rejectors
    if votes_for > votes_against:
        decision = "approved"
        confidence = (
            sum(v.confidence for v in approvals) / votes_for if votes_for > 0 else 0.0
        )
        summary = f"Approved by majority ({votes_for} for, {votes_against} against)"
    elif votes_against > votes_for:
        decision = "rejected"
        confidence = (
            sum(v.confidence for v in rejections) / votes_against
            if votes_against > 0
            else 0.0
        )
        summary = f"Rejected by majority ({votes_against} against, {votes_for} for)"
    else:
        decision = "no_consensus"
        confidence = 0.5
        summary = f"Tie vote ({votes_for} for, {votes_against} against)"

    return ConsensusResult(
        decision=decision,
        algorithm=ConsensusAlgorithm.MAJORITY,
        confidence_score=confidence,
        votes_for=votes_for,
        votes_against=votes_against,
        abstentions=abstain_count,
        summary=summary,
    )


def weighted_consensus(
    votes: list[Vote], weights: dict[str, float]
) -> ConsensusResult:
    """Weighted voting based on agent expertise.

    Each agent's vote is weighted by their expertise in the decision domain.
    Example: architect has higher weight for design decisions.

    Args:
        votes: List of agent votes
        weights: Dict mapping agent name to weight (default 1.0)

    Returns:
        ConsensusResult with weighted decision
    """
    approvals = [v for v in votes if v.position == "approve"]
    rejections = [v for v in votes if v.position == "reject"]
    abstentions = [v for v in votes if v.position == "abstain"]

    # Calculate weighted scores
    weighted_for = sum(
        weights.get(v.agent, 1.0) * v.confidence for v in approvals
    )
    weighted_against = sum(
        weights.get(v.agent, 1.0) * v.confidence for v in rejections
    )

    votes_for = len(approvals)
    votes_against = len(rejections)
    abstain_count = len(abstentions)

    # Total possible weight for participating voters
    total_weight = sum(
        weights.get(v.agent, 1.0) for v in votes if v.position != "abstain"
    )

    if weighted_for > weighted_against:
        decision = "approved"
        confidence = weighted_for / total_weight if total_weight > 0 else 0.0
        summary = (
            f"Approved by weighted vote "
            f"({weighted_for:.2f} for, {weighted_against:.2f} against)"
        )
    elif weighted_against > weighted_for:
        decision = "rejected"
        confidence = weighted_against / total_weight if total_weight > 0 else 0.0
        summary = (
            f"Rejected by weighted vote "
            f"({weighted_against:.2f} against, {weighted_for:.2f} for)"
        )
    else:
        decision = "no_consensus"
        confidence = 0.5
        summary = f"Tie in weighted vote ({weighted_for:.2f} for, {weighted_against:.2f} against)"

    return ConsensusResult(
        decision=decision,
        algorithm=ConsensusAlgorithm.WEIGHTED,
        confidence_score=confidence,
        votes_for=votes_for,
        votes_against=votes_against,
        abstentions=abstain_count,
        summary=summary,
    )


def quorum_consensus(
    votes: list[Vote], quorum_threshold: float = 0.67
) -> ConsensusResult:
    """Quorum-based consensus.

    Requires minimum participation before deciding. If quorum is not met,
    returns no_consensus. Otherwise applies majority voting.

    Args:
        votes: List of agent votes
        quorum_threshold: Minimum fraction of agents required (default 0.67 = 2/3)

    Returns:
        ConsensusResult with quorum-checked decision
    """
    if not 0.0 <= quorum_threshold <= 1.0:
        msg = f"Quorum threshold must be 0.0-1.0, got {quorum_threshold}"
        raise ValueError(msg)

    non_abstain = [v for v in votes if v.position != "abstain"]
    participation_rate = len(non_abstain) / len(votes) if votes else 0.0

    if participation_rate < quorum_threshold:
        return ConsensusResult(
            decision="no_consensus",
            algorithm=ConsensusAlgorithm.QUORUM,
            confidence_score=0.0,
            votes_for=len([v for v in votes if v.position == "approve"]),
            votes_against=len([v for v in votes if v.position == "reject"]),
            abstentions=len([v for v in votes if v.position == "abstain"]),
            summary=f"Quorum not met ({participation_rate:.1%} < {quorum_threshold:.1%})",
        )

    # Quorum met, apply majority voting
    result = majority_consensus(votes)
    result.algorithm = ConsensusAlgorithm.QUORUM
    result.summary = f"Quorum met ({participation_rate:.1%}). " + result.summary
    return result


def unanimous_consensus(votes: list[Vote]) -> ConsensusResult:
    """Unanimous consensus.

    All participating agents must agree. Single rejection blocks approval.
    Abstentions are ignored.

    Args:
        votes: List of agent votes

    Returns:
        ConsensusResult requiring unanimous agreement
    """
    approvals = [v for v in votes if v.position == "approve"]
    rejections = [v for v in votes if v.position == "reject"]
    abstentions = [v for v in votes if v.position == "abstain"]

    votes_for = len(approvals)
    votes_against = len(rejections)
    abstain_count = len(abstentions)

    # All non-abstaining votes must be approvals
    if votes_against > 0:
        decision = "rejected"
        confidence = 1.0
        summary = f"Unanimous consent failed ({votes_against} objection(s))"
    elif votes_for > 0 and votes_against == 0:
        decision = "approved"
        # Average confidence across all approvers
        confidence = sum(v.confidence for v in approvals) / votes_for
        summary = f"Unanimous approval ({votes_for} agents)"
    else:
        decision = "no_consensus"
        confidence = 0.0
        summary = "No votes cast (all abstained)"

    return ConsensusResult(
        decision=decision,
        algorithm=ConsensusAlgorithm.UNANIMOUS,
        confidence_score=confidence,
        votes_for=votes_for,
        votes_against=votes_against,
        abstentions=abstain_count,
        summary=summary,
    )
