# Consensus Mechanisms for Multi-Agent Decisions

When specialist agents disagree during impact analysis or complex decisions, the system uses formal consensus algorithms. All decisions are recorded with votes, rationale, algorithm used, and confidence scores.

## Consensus Algorithms

| Algorithm | Description | Use Cases |
|-----------|-------------|-----------|
| majority | Simple majority voting (>50% approval) | Standard decisions with equal agent expertise |
| weighted | Expertise-weighted by agent type and domain | Domain-specific decisions (architecture, security) |
| quorum | Requires minimum participation (default 67%) | Important decisions requiring broad input |
| unanimous | All participating agents must agree | Critical decisions (breaking changes, security) |

## Agent Expertise Weights

Weighted consensus uses domain-specific weights defined in `scripts/consensus/weights.py`:

| Domain | High (2.0) | Medium (1.5) | Standard (1.0) |
|--------|-----------|--------------|----------------|
| architecture | architect | independent-thinker, high-level-advisor | implementer, analyst |
| security | security | architect | implementer, analyst |
| implementation | implementer | analyst, qa | architect, devops, security |
| testing | qa | implementer | security, analyst |
| operations | devops | security | implementer, architect |
| breaking_change | architect, high-level-advisor | security | implementer, qa, devops |

## Integration Points

Consensus mechanisms are invoked during:

1. **Impact Analysis**: When multiple specialists disagree on approach
2. **ADR Reviews**: For approval requiring multiple viewpoints
3. **Security Changes**: When security and implementation conflict
4. **Breaking Changes**: Requiring unanimous or weighted consensus

## Usage

```python
from scripts.consensus import Vote, weighted_consensus, DecisionRecorder, get_all_weights

votes = [
    Vote("architect", "approve", "Design aligns with system architecture", 0.9),
    Vote("security", "reject", "Introduces authentication risk", 0.8),
    Vote("implementer", "approve", "Implementation is feasible", 0.85),
]

weights = get_all_weights("architecture")
result = weighted_consensus(votes, weights)

recorder = DecisionRecorder()
decision = recorder.record_decision(
    topic="Add OAuth authentication",
    context="Feature requires secure authentication mechanism",
    votes=votes,
    result=result,
)
```

## Decision Recording

All consensus decisions are stored in `.agents/decisions/` as JSON files containing:

- Decision ID and timestamp
- Topic and detailed context
- Individual agent votes with rationale and confidence
- Consensus result with algorithm and confidence score
- Escalation flag and rationale (if applicable)

## Escalation Path

If consensus fails (tie vote, quorum not met, blocking objection):

1. Decision is recorded with `escalated: true`
2. Escalation rationale is documented
3. Orchestrator escalates to high-level-advisor for final decision
4. Disagree-and-commit protocol is applied (see below)

## Disagree and Commit Protocol

When specialists have conflicting recommendations, apply "Disagree and Commit" to avoid endless consensus-seeking.

### Protocol Phases

**Phase 1, Decision (Dissent Encouraged)**:

- All specialists present positions with data and rationale
- Disagreements are surfaced explicitly and documented
- Critic synthesizes positions and identifies core conflicts

**Phase 2, Resolution**:

- If consensus emerges, proceed with agreed approach
- If conflict persists, escalate to high-level-advisor
- High-level-advisor decides with documented rationale

**Phase 3, Commitment (Alignment Required)**:

- All specialists commit to execution once decision is made
- No passive-aggressive execution or "I told you so" behavior
- Earlier disagreement cannot be used as excuse for poor execution

### Commitment Language

```text
"I disagree with [approach] because [reasons], but I commit to executing
[decided approach] fully. My concerns are documented for retrospective."
```

### Escalation Table

| Situation | Action |
|-----------|--------|
| Single specialist times out | Mark incomplete, proceed |
| Specialists disagree, data supports resolution | Critic decides, specialists commit |
| Specialists disagree, no clear winner | Escalate to high-level-advisor |
| High-level-advisor decides | All specialists commit and execute |
| Chronic disagreement on same topic | Flag for retrospective |
