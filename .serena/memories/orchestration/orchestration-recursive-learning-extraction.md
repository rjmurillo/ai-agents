# Skill-Orchestration-005: Recursive Learning Extraction

**Statement**: Extract learnings recursively until no novel patterns remain.

**Context**: Session retrospective workflow (post-implementation learning)

**Evidence**: Session 87 - Three extraction rounds (initial session learnings → skillbook meta-learnings → this recursive pattern itself).

**Atomicity**: 85% | **Impact**: 7/10

## Pattern

```text
1. Initial extraction: Identify learnings from session execution
   ↓
2. Skillbook delegation: Validate atomicity, check duplicates, create memories
   ↓
3. Recursive evaluation: "Are there additional learnings from extraction itself?"
   ↓
4. Termination: Stop when no new learnings OR all rejected as duplicates
```

## Termination Criteria

Stop when ANY condition is met:

- Zero new learnings identified in current round
- All proposed learnings rejected as >70% duplicate
- Three consecutive rounds with no novel patterns
- Diminishing returns (meta-meta-learnings provide no value)

## Benefits

1. **Complete capture**: Systematic approach prevents missing learnings
2. **Self-referential**: Learning extraction can itself generate learnings
3. **Bounded iteration**: Clear termination prevents infinite loops

## Anti-Pattern

```text
# WRONG: Single-pass extraction
Extract learnings → Create skills → Done
# LOSES: Meta-patterns about the extraction process itself
```

## Related

- **ENABLES**: Complete learning capture from complex sessions
- **REQUIRES**: Skillbook manager validation at each round

## Related

- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [orchestration-copilot-swe-anti-patterns](orchestration-copilot-swe-anti-patterns.md)
- [orchestration-handoff-coordination](orchestration-handoff-coordination.md)
- [orchestration-parallel-execution](orchestration-parallel-execution.md)
- [orchestration-pr-chain](orchestration-pr-chain.md)
