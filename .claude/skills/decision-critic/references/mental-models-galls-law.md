---
source: wiki/concepts/Mental Models/Galls Law.md
created: 2026-04-11
review-by: 2026-07-11
---

# Gall's Law

## Principle

Complex systems that work evolved from simple systems that worked.

> "A complex system that works is invariably found to have evolved from a simple system that worked." -- John Gall

## Corollary

A complex system designed from scratch never works and cannot be patched up to make it work. You have to start over with a working simple system.

## Decision Critic Application

Use this model during **Challenge** (Steps 5-6) to stress-test architectural proposals and system designs.

### Verification Questions

When a decision proposes building a new system or major redesign:

1. Does the proposal start with a working simple version?
2. Is the complexity justified by real feedback, or imagined future needs?
3. Can the design be decomposed into independently working subsystems?
4. Is there a "big bang" cutover, or incremental evolution?

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "We'll build it all at once" | Big bang failure |
| "We need this for future scale" | YAGNI violation, premature complexity |
| "The perfect architecture" | Designed-from-scratch trap |
| "Complete rewrite" | Ignoring evolved knowledge in existing system |
| "We'll need this someday" | Speculative features increase failure surface |

### Contrarian Perspectives (Step 5)

When reviewing system design decisions, generate these contrarian views:

- "What if we built only the simplest version that solves the immediate problem?"
- "What if we evolved the existing system instead of replacing it?"
- "What if we shipped in 3 increments instead of 1?"

### Failure Modes (for Inversion Analysis)

- System never ships because scope is too large
- Integration failures between components designed in isolation
- Real user needs diverge from upfront assumptions
- Team burns out on complexity before delivering value

## Practical Checklist

Before accepting a system design decision as VERIFIED:

- [ ] Simplest working version identified
- [ ] Evolution path from simple to complex defined
- [ ] Each increment delivers standalone value
- [ ] No speculative features included

## Related Models

- Chesterton's Fence: understand existing systems before replacing
- YAGNI: do not build for imagined future needs
- Strangler Fig: incremental migration pattern
