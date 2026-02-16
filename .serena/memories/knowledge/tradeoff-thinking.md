# Tradeoff Thinking Framework

**Category**: Engineering Decision-Making
**Source**: `.agents/analysis/senior-engineering-knowledge.md`

## Core Principle

Every engineering decision involves tradeoffs. Senior engineers recognize these explicitly rather than pretending optimal solutions exist.

## Common Tradeoff Pairs

| Tradeoff | Resolution Guidance |
|----------|---------------------|
| Speed vs Safety | Context-dependent: prototype vs production |
| Complexity vs Flexibility | Start specific, generalize when patterns emerge |
| Explicitness vs Abstraction | Prefer explicit until duplication hurts |
| Coupling vs Duplication | Copy DTOs between services; share only stable contracts |

## Decision Framework

1. **Name the tradeoff explicitly**: "We're trading X for Y"
2. **Quantify if possible**: "This adds 2 days but reduces risk by 40%"
3. **Document the decision**: ADR captures context
4. **Set review triggers**: "Revisit if throughput exceeds 10K/sec"

## Coupling vs Duplication

Conventional wisdom says DRY. Senior insight: coupling is often worse.

**When to duplicate**: DTOs between services, config between environments, test fixtures
**When to share**: Stable domain concepts, security logic, core business rules

## Related

- [technical-debt-quadrant](technical-debt-quadrant.md) - Types of acceptable debt
- [yagni-principle](yagni-principle.md) - Build only what's needed
- [adr-foundational-concepts](adr-foundational-concepts.md) - Decision documentation
