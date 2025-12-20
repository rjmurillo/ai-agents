# ADR-010: Quality Gates with Evaluator-Optimizer Pattern

## Status

Accepted

## Date

2025-12-20

## Context

The ai-agents system has implicit quality checks through the critic agent, but no formalized evaluation loop:

1. **Single-pass generation**: Agents produce output once, critic reviews
2. **Binary outcomes**: Pass/fail with no structured feedback for improvement
3. **No iteration cap**: Unclear when to stop refining
4. **Subjective criteria**: Quality assessment varies by reviewer

Research into [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) revealed the SPARC methodology:

- 5 phases with explicit quality gates between each
- 17 operational modes for different task types
- Generator-Evaluator-Regenerate loop with structured feedback
- Hard cap at 3 iterations to prevent infinite loops

This aligns with Anthropic's evaluator-optimizer pattern from their agent design guidance.

## Decision

**All significant outputs MUST pass through a formalized evaluator-optimizer loop.**

Specifically:

1. **Evaluation rubric**: Completeness (25%), Correctness (25%), Clarity (25%), Actionability (25%)
2. **Structured feedback**: Evaluator returns scores + specific improvement suggestions
3. **Regeneration limit**: Maximum 3 iterations before escalation
4. **Termination criteria**: Score >= 70% OR iterations >= 3

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Single pass + review | Fast | Quality inconsistent | Current approach |
| Unlimited iteration | Thorough | May never terminate | Infinite loop risk |
| Fixed iteration (3) | Bounded, improves | May not reach quality | **Chosen** (with escalation) |

### Trade-offs

- **Latency**: Each iteration adds round-trip time
- **Token cost**: Regeneration consumes additional tokens
- **Diminishing returns**: Iteration 3 rarely better than iteration 2

## Consequences

### Positive

- Consistent quality baseline across all outputs
- Structured improvement rather than vague "make it better"
- Bounded execution prevents runaway loops
- Metrics enable quality tracking over time

### Negative

- Slower output for complex artifacts
- Evaluation overhead for simple tasks
- Risk of over-optimization on metrics vs actual quality

### Neutral

- independent-thinker agent evolves to formal evaluator role

## Implementation Notes

### Evaluation Rubric

| Criterion | Weight | Description | Scoring |
|-----------|--------|-------------|---------|
| Completeness | 25% | All requirements addressed | 0-25 |
| Correctness | 25% | No factual errors | 0-25 |
| Clarity | 25% | Unambiguous language | 0-25 |
| Actionability | 25% | Can be executed without clarification | 0-25 |

### Loop Protocol

```text
1. Generator produces output
2. Evaluator scores against rubric
3. If score >= 70%: ACCEPT
4. If score < 70% AND iteration < 3:
   - Evaluator provides specific feedback
   - Generator regenerates with feedback
   - Go to step 2
5. If iteration >= 3: ESCALATE to user
```

### Phase 5 Implementation Order

1. Define evaluation rubric (this ADR)
2. Update independent-thinker with scoring output (Issue #172)
3. Add regeneration capability to orchestrator
4. Implement evaluation history tracking
5. Add metrics to session logs

### When to Apply

| Output Type | Evaluation Required? | Rationale |
|-------------|---------------------|-----------|
| PRD / Spec | Yes | High impact, worth iteration |
| Code implementation | Yes | Correctness critical |
| Simple queries | No | Overhead exceeds value |
| Documentation fixes | Optional | Depends on scope |

## Related Decisions

- ADR-007: Memory-First Architecture (evaluations stored for learning)
- ADR-009: Parallel-Safe Multi-Agent Design (parallel evaluation possible)
- `.agents/governance/consistency-protocol.md` (existing quality checks)

## References

- Epic #183: Claude-Flow Inspired Enhancements
- Issue #172: SPARC-like Methodology
- [claude-flow SPARC documentation](https://github.com/ruvnet/claude-flow)
- [Anthropic evaluator-optimizer pattern](https://www.anthropic.com/engineering/building-effective-agents)
- `.agents/planning/enhancement-PROJECT-PLAN.md` Phase 5

---

*Template Version: 1.0*
*Origin: Epic #183 closing comment (2025-12-20)*
