# Multi-Agent Consensus Decisions

This directory stores decisions made through multi-agent consensus mechanisms.

## Purpose

When specialist agents disagree during impact analysis or complex decisions, the system uses consensus algorithms to reach a decision. All decisions are recorded here for traceability and future reference.

## Decision Format

Each decision is stored as a JSON file with the following structure:

```json
{
  "id": "decision-2026-02-06T14-30-00-123456+00-00",
  "timestamp": "2026-02-06T14:30:00.123456+00:00",
  "topic": "Brief description of the decision",
  "context": "Detailed context explaining the situation",
  "votes": [
    {
      "agent": "architect",
      "position": "approve",
      "rationale": "Design aligns with system architecture",
      "confidence": 0.9
    },
    {
      "agent": "security",
      "position": "reject",
      "rationale": "Introduces authentication risk",
      "confidence": 0.8
    }
  ],
  "result": {
    "decision": "approved",
    "algorithm": "weighted",
    "confidence_score": 0.75,
    "votes_for": 3,
    "votes_against": 1,
    "abstentions": 0,
    "summary": "Approved by weighted vote (5.40 for, 0.80 against)"
  },
  "escalated": false,
  "escalation_rationale": ""
}
```

## Consensus Algorithms

### Majority
Simple majority voting. More approvals than rejections results in approval.
- Use for: Standard decisions with equal agent expertise
- Threshold: >50% approval

### Weighted
Expertise-weighted voting based on agent type and decision domain.
- Use for: Domain-specific decisions (architecture, security, etc.)
- Weights defined in `scripts/consensus/weights.py`

### Quorum
Requires minimum participation (default 67%) before deciding.
- Use for: Important decisions requiring broad input
- Falls back to majority voting if quorum met

### Unanimous
All participating agents must agree. Single rejection blocks approval.
- Use for: Critical decisions (breaking changes, security-sensitive)
- Abstentions are ignored

## Integration Points

Consensus mechanisms are invoked during:

1. **Impact Analysis Consultations**: When multiple specialists disagree on approach
2. **Architecture Decision Reviews**: For ADR approval requiring multiple viewpoints
3. **Security-Sensitive Changes**: When security and implementation conflict
4. **Breaking Change Approvals**: Requiring unanimous or weighted consensus

## Escalation Path

If consensus fails (tie vote, quorum not met, etc.):
1. Decision is recorded with `escalated: true`
2. Escalation rationale is documented
3. Orchestrator escalates to high-level-advisor for final decision
4. Disagree-and-commit protocol is applied

## Usage Example

```python
from scripts.consensus import (
    Vote,
    majority_consensus,
    DecisionRecorder,
)

# Collect votes from agents
votes = [
    Vote("architect", "approve", "Design is sound", 0.9),
    Vote("security", "reject", "Security risk present", 0.8),
    Vote("implementer", "approve", "Implementation feasible", 0.85),
]

# Apply consensus algorithm
result = majority_consensus(votes)

# Record decision
recorder = DecisionRecorder()
decision = recorder.record_decision(
    topic="Add OAuth authentication",
    context="Feature requires secure authentication mechanism",
    votes=votes,
    result=result,
)

print(f"Decision: {result.decision}")
print(f"Confidence: {result.confidence_score:.2f}")
print(f"Summary: {result.summary}")
```

## Viewing Decisions

List recent decisions:

```python
from scripts.consensus import DecisionRecorder

recorder = DecisionRecorder()

# Get 10 most recent decisions
recent = recorder.list_decisions(limit=10)

# Filter by topic
auth_decisions = recorder.list_decisions(topic_filter="authentication")

# Get specific decision
decision = recorder.get_decision("decision-2026-02-06T14-30-00")
```

## References

- Implementation: `scripts/consensus/`
- Tests: `tests/test_consensus.py`
- Analysis: `.agents/analysis/claude-flow-architecture-analysis.md`
- Claude-flow reference: Section 8.4 Consensus and Decision Making
