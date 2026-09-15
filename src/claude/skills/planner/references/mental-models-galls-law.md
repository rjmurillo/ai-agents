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

## Planner Application

Use Gall's Law during **planning steps** and **review phase** to validate milestone decomposition.

### Planning Verification Questions

When breaking a task into milestones, verify each milestone against:

1. Does each milestone produce a working, independently testable result?
2. Is milestone 1 the simplest possible version that delivers value?
3. Does each subsequent milestone evolve complexity incrementally?
4. Are there any milestones that only work when combined with others?

### Red Flags in Plans

| Signal | Risk | Fix |
|--------|------|-----|
| Milestone 1 has 5+ dependencies | System designed from scratch | Reduce M1 to zero-dependency proof of concept |
| "Phase 1: Build infrastructure" | No user value until later phases | Deliver thin vertical slice in M1 |
| All milestones required for first demo | Big bang integration risk | Ensure M1 is independently demonstrable |
| Speculative features in any milestone | YAGNI violation | Remove until real feedback demands them |

### Review Phase Application

During TW + QR review (planner.py review steps 1-2):

- **TW (Step 1)**: Check that milestone descriptions avoid temporal contamination about "future phases" that imply the current phase has no standalone value.
- **QR (Step 2)**: Validate that each milestone can be shipped independently. If a milestone depends on subsequent milestones to be useful, flag it.

### Practical Checklist

Before approving a plan:

- [ ] Milestone 1 is the simplest working version
- [ ] Each milestone delivers standalone value
- [ ] Evolution path from simple to complex is explicit
- [ ] No speculative features in any milestone
- [ ] Each milestone is independently testable

## Related Models

- Chesterton's Fence: understand existing systems before replacing
- YAGNI: do not build for imagined future needs
- Strangler Fig: incremental migration over big-bang rewrite
