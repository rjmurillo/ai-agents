# Technical Debt Quadrant

**Created**: 2026-01-10
**Category**: Mental Models / Code Quality

## The Framework

Two axes create four types of technical debt:

| | Reckless | Prudent |
|---|----------|---------|
| **Deliberate** | "We don't have time for design" | "We must ship now and deal with consequences" |
| **Inadvertent** | "What's layering?" | "Now we know how we should have done it" |

**Attribution**: Martin Fowler, building on Ward Cunningham's debt metaphor

## The Four Types

### Reckless & Deliberate

- Knowingly taking shortcuts
- Underestimating design payoff
- Usually unwise

**Example**: Skipping tests to meet deadline despite knowing better.

### Prudent & Deliberate

- Calculated trade-off
- Explicit payoff evaluation
- Acceptable when benefits > costs

**Example**: Shipping with known performance issue because release timing is critical, with planned optimization sprint.

### Reckless & Inadvertent

- Poor design from ignorance
- Not really "debt" - just bad code
- Significant interest payments

**Example**: Tightly coupled code from developer who doesn't know SOLID.

### Prudent & Inadvertent

- Learning reveals better approaches
- Inevitable for good teams
- Normal and healthy

**Example**: Realizing after a year that a different architecture would have been better.

## Application to This Project

**When reviewing debt decisions**:

1. Is this prudent or reckless?
2. Is this deliberate or inadvertent?
3. Only prudent debt is acceptable
4. Deliberate debt needs explicit payoff plan

**When creating debt**:

1. Document the decision (ADR)
2. Create tracking issue
3. Define payoff criteria
4. Schedule remediation

## Key Insight

A mess is not a debt. Reckless/inadvertent code is just bad code that needs fixing, not strategic debt.

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- ADR process for documenting deliberate decisions
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
