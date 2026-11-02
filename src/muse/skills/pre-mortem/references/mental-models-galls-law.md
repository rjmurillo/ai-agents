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

## Pre-Mortem Application

Use Gall's Law during **Phase 3 (Independent Analysis)** and **Phase 5 (Review and Mitigate)** to surface complexity-driven risks.

### Risk Generation Prompts

When brainstorming failure causes, test the project against these questions:

1. Does the project attempt to build a complex system from scratch?
2. Are multiple interdependent components expected to work together on first delivery?
3. Is there a "big bang" launch rather than incremental rollout?
4. Are speculative features included that no user has requested yet?

### Red Flags That Predict Failure

| Signal | Risk Category | Typical Score |
|--------|---------------|---------------|
| "Build it all at once" | Technical | Likelihood 4, Impact 5 |
| "We need this for future scale" | Technical | Likelihood 3, Impact 3 |
| "Complete rewrite of existing system" | Process | Likelihood 4, Impact 5 |
| "All teams migrate simultaneously" | Organizational | Likelihood 3, Impact 4 |
| No working prototype exists | Technical | Likelihood 4, Impact 4 |

### Mitigation Patterns

For risks identified through Gall's Law analysis:

- **Prevention**: Decompose into independently deployable increments. Each increment must deliver standalone value.
- **Detection**: Define a "simplest working version" milestone early. If that milestone slips, the full system is at risk.
- **Response**: Cut scope to the simplest working version. Ship it. Evolve from there.

## Related Models

- Chesterton's Fence: understand existing systems before replacing
- YAGNI: do not build for imagined future needs
- Strangler Fig: incremental migration over big-bang rewrite
