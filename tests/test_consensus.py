"""Tests for consensus algorithms and decision recording.

These tests verify the consensus mechanisms for multi-agent decision making.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.consensus.algorithms import (
    ConsensusAlgorithm,
    Vote,
    majority_consensus,
    quorum_consensus,
    unanimous_consensus,
    weighted_consensus,
)
from scripts.consensus.decision_recorder import DecisionRecorder
from scripts.consensus.weights import get_agent_weight, get_all_weights


class TestVote:
    """Tests for Vote dataclass."""

    def test_valid_vote(self) -> None:
        """Valid vote with all attributes is created."""
        vote = Vote(
            agent="architect",
            position="approve",
            rationale="Design is sound",
            confidence=0.9,
        )

        assert vote.agent == "architect"
        assert vote.position == "approve"
        assert vote.rationale == "Design is sound"
        assert vote.confidence == 0.9

    def test_default_confidence(self) -> None:
        """Default confidence is 1.0."""
        vote = Vote(agent="security", position="reject", rationale="Security risk")

        assert vote.confidence == 1.0

    def test_invalid_confidence_high(self) -> None:
        """Confidence above 1.0 is rejected."""
        with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
            Vote(
                agent="qa", position="approve", rationale="Test", confidence=1.5
            )

    def test_invalid_confidence_low(self) -> None:
        """Confidence below 0.0 is rejected."""
        with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
            Vote(
                agent="qa", position="approve", rationale="Test", confidence=-0.1
            )


class TestMajorityConsensus:
    """Tests for simple majority voting."""

    def test_clear_approval(self) -> None:
        """Majority approval results in approved decision."""
        votes = [
            Vote("architect", "approve", "Good design", 0.9),
            Vote("security", "approve", "Secure", 0.8),
            Vote("implementer", "reject", "Complex", 0.7),
        ]

        result = majority_consensus(votes)

        assert result.decision == "approved"
        assert result.algorithm == ConsensusAlgorithm.MAJORITY
        assert result.votes_for == 2
        assert result.votes_against == 1
        assert result.abstentions == 0
        assert 0.8 <= result.confidence_score <= 0.9

    def test_clear_rejection(self) -> None:
        """Majority rejection results in rejected decision."""
        votes = [
            Vote("architect", "reject", "Poor design", 0.9),
            Vote("security", "reject", "Insecure", 0.8),
            Vote("implementer", "approve", "Easy to code", 0.7),
        ]

        result = majority_consensus(votes)

        assert result.decision == "rejected"
        assert result.votes_for == 1
        assert result.votes_against == 2

    def test_tie_vote(self) -> None:
        """Tie vote results in no consensus."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "reject", "Bad", 0.8),
        ]

        result = majority_consensus(votes)

        assert result.decision == "no_consensus"
        assert result.confidence_score == 0.5

    def test_abstentions_ignored(self) -> None:
        """Abstentions do not count toward majority."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "abstain", "Not my domain", 1.0),
            Vote("implementer", "abstain", "No opinion", 1.0),
        ]

        result = majority_consensus(votes)

        assert result.decision == "approved"
        assert result.votes_for == 1
        assert result.votes_against == 0
        assert result.abstentions == 2

    def test_empty_votes_raises_error(self) -> None:
        """Empty vote list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot determine consensus from empty vote list"):
            majority_consensus([])


class TestWeightedConsensus:
    """Tests for expertise-weighted voting."""

    def test_weighted_approval(self) -> None:
        """Higher-weighted agent's vote influences decision."""
        votes = [
            Vote("architect", "approve", "Good design", 0.9),
            Vote("implementer", "reject", "Complex", 0.8),
        ]
        weights = {"architect": 2.0, "implementer": 1.0}

        result = weighted_consensus(votes, weights)

        assert result.decision == "approved"
        assert result.algorithm == ConsensusAlgorithm.WEIGHTED
        # architect (2.0 * 0.9 = 1.8) > implementer (1.0 * 0.8 = 0.8)

    def test_equal_weights_fallback(self) -> None:
        """Equal weights behave like majority voting."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "reject", "Bad", 0.9),
        ]
        weights = {"architect": 1.0, "security": 1.0}

        result = weighted_consensus(votes, weights)

        assert result.decision == "no_consensus"
        assert result.confidence_score == 0.5

    def test_default_weight_applied(self) -> None:
        """Agents not in weights dict get default 1.0."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("unknown-agent", "reject", "Bad", 0.8),
        ]
        weights = {"architect": 2.0}

        result = weighted_consensus(votes, weights)

        assert result.decision == "approved"

    def test_weighted_rejection(self) -> None:
        """Higher-weighted rejector causes rejection."""
        votes = [
            Vote("architect", "approve", "Good design", 0.8),
            Vote("security", "reject", "Critical vulnerability", 0.9),
        ]
        weights = {"architect": 1.0, "security": 2.0}

        result = weighted_consensus(votes, weights)

        assert result.decision == "rejected"
        assert result.algorithm == ConsensusAlgorithm.WEIGHTED
        # security (2.0 * 0.9 = 1.8) > architect (1.0 * 0.8 = 0.8)

    def test_empty_votes_raises_error(self) -> None:
        """Empty vote list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot determine consensus from empty vote list"):
            weighted_consensus([], {})


class TestQuorumConsensus:
    """Tests for quorum-based voting."""

    def test_quorum_met_approval(self) -> None:
        """Quorum met with majority approval."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "approve", "Secure", 0.8),
            Vote("implementer", "reject", "Complex", 0.7),
        ]

        result = quorum_consensus(votes, quorum_threshold=0.67)

        assert result.decision == "approved"
        assert result.algorithm == ConsensusAlgorithm.QUORUM
        assert "Quorum met" in result.summary

    def test_quorum_not_met(self) -> None:
        """Quorum not met results in no consensus."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "abstain", "No opinion", 1.0),
            Vote("implementer", "abstain", "No opinion", 1.0),
        ]

        result = quorum_consensus(votes, quorum_threshold=0.67)

        assert result.decision == "no_consensus"
        assert "Quorum not met" in result.summary
        assert result.confidence_score == 0.0

    def test_custom_threshold(self) -> None:
        """Custom quorum threshold is respected."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "approve", "Secure", 0.8),
            Vote("implementer", "abstain", "No opinion", 1.0),
        ]

        # 50% quorum (2 of 3 voting)
        result = quorum_consensus(votes, quorum_threshold=0.5)

        assert result.decision == "approved"

    def test_invalid_threshold(self) -> None:
        """Invalid threshold raises ValueError."""
        votes = [Vote("architect", "approve", "Good", 0.9)]

        with pytest.raises(ValueError, match="Quorum threshold must be 0.0-1.0"):
            quorum_consensus(votes, quorum_threshold=1.5)

    def test_empty_votes_raises_error(self) -> None:
        """Empty vote list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot determine consensus from empty vote list"):
            quorum_consensus([])


class TestUnanimousConsensus:
    """Tests for unanimous voting."""

    def test_unanimous_approval(self) -> None:
        """All votes approve results in approval."""
        votes = [
            Vote("architect", "approve", "Perfect", 0.9),
            Vote("security", "approve", "Secure", 0.8),
            Vote("implementer", "approve", "Simple", 0.85),
        ]

        result = unanimous_consensus(votes)

        assert result.decision == "approved"
        assert result.algorithm == ConsensusAlgorithm.UNANIMOUS
        assert "Unanimous approval" in result.summary
        # Average confidence: (0.9 + 0.8 + 0.85) / 3 ≈ 0.85
        assert 0.84 <= result.confidence_score <= 0.86

    def test_single_rejection_blocks(self) -> None:
        """Single rejection blocks unanimous approval."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "reject", "Security flaw", 0.8),
            Vote("implementer", "approve", "Easy", 0.85),
        ]

        result = unanimous_consensus(votes)

        assert result.decision == "rejected"
        assert "Unanimous consent failed" in result.summary
        assert result.confidence_score == 1.0

    def test_abstentions_ignored(self) -> None:
        """Abstentions do not block unanimous approval."""
        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "abstain", "Not my domain", 1.0),
            Vote("implementer", "approve", "Easy", 0.8),
        ]

        result = unanimous_consensus(votes)

        assert result.decision == "approved"
        assert result.votes_for == 2
        assert result.abstentions == 1

    def test_all_abstain(self) -> None:
        """All abstentions result in no consensus."""
        votes = [
            Vote("architect", "abstain", "No opinion", 1.0),
            Vote("security", "abstain", "No opinion", 1.0),
        ]

        result = unanimous_consensus(votes)

        assert result.decision == "no_consensus"
        assert "all abstained" in result.summary

    def test_empty_votes_raises_error(self) -> None:
        """Empty vote list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot determine consensus from empty vote list"):
            unanimous_consensus([])


class TestAgentWeights:
    """Tests for agent expertise weights."""

    def test_get_architect_architecture_weight(self) -> None:
        """Architect has high weight in architecture domain."""
        weight = get_agent_weight("architect", "architecture")

        assert weight == 2.0

    def test_get_security_security_weight(self) -> None:
        """Security agent has high weight in security domain."""
        weight = get_agent_weight("security", "security")

        assert weight == 2.0

    def test_get_default_weight(self) -> None:
        """Unknown agent gets default weight 1.0."""
        weight = get_agent_weight("unknown-agent", "architecture")

        assert weight == 1.0

    def test_get_all_weights(self) -> None:
        """Get all weights for a domain returns dict."""
        weights = get_all_weights("architecture")

        assert isinstance(weights, dict)
        assert weights["architect"] == 2.0
        assert "implementer" in weights

    def test_get_all_weights_returns_copy(self) -> None:
        """Returned weights dict is a copy, not a mutable reference."""
        weights = get_all_weights("architecture")
        original_value = weights["architect"]

        # Mutate the returned dict
        weights["architect"] = 999.0

        # Verify internal state is unchanged
        fresh_weights = get_all_weights("architecture")
        assert fresh_weights["architect"] == original_value


class TestDecisionRecorder:
    """Tests for decision recording and storage."""

    def test_record_decision(self, tmp_path: Path) -> None:
        """Decision is recorded to JSON file."""
        recorder = DecisionRecorder(tmp_path)

        votes = [
            Vote("architect", "approve", "Good design", 0.9),
            Vote("security", "approve", "Secure", 0.8),
        ]
        result = majority_consensus(votes)

        decision = recorder.record_decision(
            topic="Add OAuth authentication",
            context="Feature requires secure authentication",
            votes=votes,
            result=result,
        )

        assert decision.id.startswith("decision-")
        assert decision.topic == "Add OAuth authentication"
        assert len(decision.votes) == 2

        # Check file was created
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_get_decision(self, tmp_path: Path) -> None:
        """Recorded decision can be retrieved by ID."""
        recorder = DecisionRecorder(tmp_path)

        votes = [Vote("architect", "approve", "Good", 0.9)]
        result = majority_consensus(votes)
        recorded = recorder.record_decision(
            topic="Test decision", context="Test", votes=votes, result=result
        )

        retrieved = recorder.get_decision(recorded.id)

        assert retrieved is not None
        assert retrieved.id == recorded.id
        assert retrieved.topic == "Test decision"

    def test_get_nonexistent_decision(self, tmp_path: Path) -> None:
        """Retrieving nonexistent decision returns None."""
        recorder = DecisionRecorder(tmp_path)

        decision = recorder.get_decision("nonexistent-id")

        assert decision is None

    def test_list_decisions(self, tmp_path: Path) -> None:
        """List returns all recorded decisions."""
        recorder = DecisionRecorder(tmp_path)

        votes = [Vote("architect", "approve", "Good", 0.9)]
        result = majority_consensus(votes)

        recorder.record_decision(
            topic="Decision 1", context="Test", votes=votes, result=result
        )
        recorder.record_decision(
            topic="Decision 2", context="Test", votes=votes, result=result
        )

        decisions = recorder.list_decisions()

        assert len(decisions) == 2

    def test_list_with_limit(self, tmp_path: Path) -> None:
        """List respects limit parameter."""
        recorder = DecisionRecorder(tmp_path)

        votes = [Vote("architect", "approve", "Good", 0.9)]
        result = majority_consensus(votes)

        for i in range(5):
            recorder.record_decision(
                topic=f"Decision {i}", context="Test", votes=votes, result=result
            )

        decisions = recorder.list_decisions(limit=3)

        assert len(decisions) == 3

    def test_list_with_invalid_limit(self, tmp_path: Path) -> None:
        """Limit of 0 or negative raises ValueError."""
        recorder = DecisionRecorder(tmp_path)

        with pytest.raises(ValueError, match="Limit must be >= 1"):
            recorder.list_decisions(limit=0)

        with pytest.raises(ValueError, match="Limit must be >= 1"):
            recorder.list_decisions(limit=-1)

    def test_list_with_topic_filter(self, tmp_path: Path) -> None:
        """List filters by topic substring."""
        recorder = DecisionRecorder(tmp_path)

        votes = [Vote("architect", "approve", "Good", 0.9)]
        result = majority_consensus(votes)

        recorder.record_decision(
            topic="Add authentication", context="Test", votes=votes, result=result
        )
        recorder.record_decision(
            topic="Update database", context="Test", votes=votes, result=result
        )
        recorder.record_decision(
            topic="Add authorization", context="Test", votes=votes, result=result
        )

        decisions = recorder.list_decisions(topic_filter="auth")

        assert len(decisions) == 2
        assert all("auth" in d.topic.lower() for d in decisions)

    def test_escalation_recorded(self, tmp_path: Path) -> None:
        """Escalation flag and rationale are recorded."""
        recorder = DecisionRecorder(tmp_path)

        votes = [
            Vote("architect", "approve", "Good", 0.9),
            Vote("security", "reject", "Bad", 0.9),
        ]
        result = majority_consensus(votes)

        decision = recorder.record_decision(
            topic="Controversial decision",
            context="Strong disagreement",
            votes=votes,
            result=result,
            escalated=True,
            escalation_rationale="Tie requires high-level-advisor decision",
        )

        assert decision.escalated is True
        assert "high-level-advisor" in decision.escalation_rationale

    def test_decision_json_format(self, tmp_path: Path) -> None:
        """Recorded JSON has correct structure."""
        recorder = DecisionRecorder(tmp_path)

        votes = [Vote("architect", "approve", "Good", 0.9)]
        result = majority_consensus(votes)
        decision = recorder.record_decision(
            topic="Test", context="Test", votes=votes, result=result
        )

        filepath = tmp_path / f"{decision.id}.json"
        with filepath.open(encoding="utf-8") as f:
            data = json.load(f)

        assert "id" in data
        assert "timestamp" in data
        assert "topic" in data
        assert "context" in data
        assert "votes" in data
        assert "result" in data
        assert isinstance(data["votes"], list)
        assert isinstance(data["result"], dict)
