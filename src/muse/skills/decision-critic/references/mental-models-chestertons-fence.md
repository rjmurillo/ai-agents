---
source: wiki/concepts/Mental Models/Chestertons Fence.md
created: 2026-04-11
review-by: 2026-07-11
---

# Chesterton's Fence

## Principle

Before removing or changing something, first understand why it exists.

> "Don't ever take a fence down until you know the reason it was put up." -- G.K. Chesterton

## Decision Critic Application

Use this model during **Decomposition** (Steps 1-2) to surface hidden assumptions about existing systems.

### Verification Questions

When a decision proposes removing, replacing, or deprecating something:

1. What problem did the existing thing originally solve?
2. Are those original constraints still active?
3. What implicit dependencies exist that the proposer may not see?
4. Has anyone consulted the people who built it?

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "This is legacy, remove it" | Original constraints unknown |
| "Nobody knows why this exists" | Institutional knowledge gap |
| "We don't need this anymore" | Implicit dependencies unexamined |
| "Let's start fresh" | Second System Effect risk |

### Failure Modes (for Inversion Analysis)

- Reintroducing bugs that were previously fixed
- Breaking implicit dependencies downstream
- Losing institutional knowledge permanently
- Triggering cascading failures in systems coupled to the removed component

## Practical Checklist

Before accepting a "remove/replace" decision as VERIFIED:

- [ ] Original purpose documented or discovered
- [ ] Current constraints compared to original constraints
- [ ] Downstream dependencies mapped
- [ ] Migration path defined (not just deletion)

## Related Models

- Gall's Law: complex systems evolved from simple ones
- Strangler Fig Pattern: incremental migration respects existing behavior
- Hyrum's Law: changing observable behavior breaks unknown dependents
