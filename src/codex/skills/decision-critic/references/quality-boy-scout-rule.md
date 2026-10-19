---
source: wiki/concepts/Mental Models/Boy Scout Rule.md
created: 2026-04-11
review-by: 2026-07-11
tailored-for: decision-critic
---

# Boy Scout Rule

> "Always leave the codebase cleaner than you found it."

Attribution: Robert C. Martin (Uncle Bob)

## Core Insight

Make small improvements continuously. Do not wait for dedicated refactoring sprints. Incremental improvement prevents rot. Compounding effect over time.

## Decision Critique Application

When evaluating decisions that involve code changes, assess scope boundaries:

| Claim Type | Critique Question |
|------------|-------------------|
| "While fixing this, I should also..." | Is the additional work within the touched area? |
| "This needs refactoring first" | Can the fix proceed without the refactor? |
| "I'll clean this up while I'm here" | Will cleanup delay delivery? |

## Boundaries for Critique

When validating improvement decisions:

| VERIFIED | FAILED | UNCERTAIN |
|----------|--------|-----------|
| Change is in touched code area | Change unrelated to current work | Scope unclear from context |
| Small, safe improvement | Large refactoring bundled with fix | Risk assessment missing |
| Balanced with delivery | Perfectionism blocking progress | Trade-offs not articulated |

## Warning Signs to Flag

During decision critique, flag these patterns:

- "While I'm here" expanding to major work
- Scope creep in PRs
- Delivery blocked by improvement claims
- No clear connection between improvement and original goal

## Synthesis Guidance

When reaching verdict on improvement decisions:

- **STAND**: Improvement clearly scoped to touched area, safe, and not blocking delivery
- **REVISE**: Scope unclear or trade-offs not addressed; needs boundary clarification
- **ESCALATE**: Large refactoring masquerading as small improvement; requires separate planning

## Related Concepts

- **Chesterton's Fence**: Understand before changing
- **Strangler Fig Pattern**: Incremental migration for larger changes
