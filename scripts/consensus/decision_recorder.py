"""Decision recording and storage for multi-agent consensus.

Records decisions with votes, rationale, algorithm used, and confidence scores.
Stores decisions as JSON files in .agents/decisions/ directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.consensus.algorithms import ConsensusResult, Vote


@dataclass
class Decision:
    """Recorded multi-agent decision.

    Attributes:
        id: Unique decision identifier (timestamp-based)
        timestamp: ISO 8601 timestamp when decision was made
        topic: Brief description of decision topic
        context: Detailed context explaining the decision situation
        votes: List of individual agent votes with rationale
        result: Consensus result with algorithm and confidence
        escalated: Whether decision was escalated to high-level-advisor
        escalation_rationale: Reason for escalation (if applicable)
    """

    id: str
    timestamp: str
    topic: str
    context: str
    votes: list[dict[str, str | float]]
    result: dict[str, str | float | int]
    escalated: bool = False
    escalation_rationale: str = ""


class DecisionRecorder:
    """Records and retrieves multi-agent consensus decisions."""

    def __init__(self, decisions_dir: Path | None = None) -> None:
        """Initialize decision recorder.

        Args:
            decisions_dir: Directory for storing decisions
                          (default: .agents/decisions/)
        """
        if decisions_dir is None:
            decisions_dir = Path(".agents/decisions")
        self.decisions_dir = decisions_dir
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def record_decision(
        self,
        topic: str,
        context: str,
        votes: list[Vote],
        result: ConsensusResult,
        escalated: bool = False,
        escalation_rationale: str = "",
    ) -> Decision:
        """Record a decision to storage.

        Args:
            topic: Brief description of decision topic
            context: Detailed context for the decision
            votes: List of agent votes
            result: Consensus result
            escalated: Whether escalated to high-level-advisor
            escalation_rationale: Reason for escalation

        Returns:
            Recorded Decision object
        """
        timestamp = datetime.now(UTC).isoformat()
        decision_id = self._generate_id(timestamp)

        # Convert dataclasses to dicts
        votes_dict = [asdict(v) for v in votes]
        result_dict = {
            "decision": result.decision,
            "algorithm": result.algorithm.value,
            "confidence_score": result.confidence_score,
            "votes_for": result.votes_for,
            "votes_against": result.votes_against,
            "abstentions": result.abstentions,
            "summary": result.summary,
        }

        decision = Decision(
            id=decision_id,
            timestamp=timestamp,
            topic=topic,
            context=context,
            votes=votes_dict,
            result=result_dict,
            escalated=escalated,
            escalation_rationale=escalation_rationale,
        )

        # Write to file
        filepath = self.decisions_dir / f"{decision_id}.json"
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(asdict(decision), f, indent=2, ensure_ascii=False)

        return decision

    def get_decision(self, decision_id: str) -> Decision | None:
        """Retrieve a decision by ID.

        Args:
            decision_id: Decision identifier

        Returns:
            Decision object or None if not found
        """
        filepath = self.decisions_dir / f"{decision_id}.json"
        if not filepath.exists():
            return None

        with filepath.open(encoding="utf-8") as f:
            data = json.load(f)

        return Decision(**data)

    def list_decisions(
        self, limit: int | None = None, topic_filter: str | None = None
    ) -> list[Decision]:
        """List recorded decisions.

        Args:
            limit: Maximum number of decisions to return (newest first)
            topic_filter: Filter by topic substring (case-insensitive)

        Returns:
            List of Decision objects
        """
        files = sorted(
            self.decisions_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        decisions = []
        for filepath in files:
            with filepath.open(encoding="utf-8") as f:
                data = json.load(f)
                decision = Decision(**data)

                # Apply topic filter
                if topic_filter and topic_filter.lower() not in decision.topic.lower():
                    continue

                decisions.append(decision)

                # Apply limit
                if limit and len(decisions) >= limit:
                    break

        return decisions

    def _generate_id(self, timestamp: str) -> str:
        """Generate unique decision ID from timestamp.

        Args:
            timestamp: ISO 8601 timestamp

        Returns:
            Decision ID (e.g., "decision-2026-02-06T14-30-00-123456")
        """
        # Convert ISO timestamp to filesystem-safe format
        # Include microseconds to ensure uniqueness for rapid decisions
        safe_timestamp = timestamp.replace(":", "-").replace(".", "-")
        return f"decision-{safe_timestamp}"
