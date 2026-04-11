---
source: wiki/concepts/Mental Models/Boy Scout Rule.md
created: 2026-04-11
review-by: 2026-07-11
---

# Boy Scout Rule

## The Rule

> "Always leave the codebase cleaner than you found it." -- Robert C. Martin

## Core Insight

Make small improvements continuously. Incremental improvement prevents rot. Do not wait for dedicated refactoring sprints.

## Decision Critic Application

Use this model during **Verification** (Steps 3-4) to evaluate scope boundaries in refactoring and improvement decisions.

### Verification Questions

When a decision includes "while we're at it" improvements:

1. Is the improvement related to the primary change?
2. Is the change small and safe, or a large refactoring?
3. Does the improvement block delivery?
4. Is the scope creep justified by testability or correctness gains?

### Boundaries Matrix

| Do | Do Not |
|----|--------|
| Related improvements in touched files | Unrelated gold-plating |
| Small, safe, localized changes | Large refactorings disguised as cleanup |
| Improvements in current area of code | Wandering through the codebase |
| Balance cleanup with delivery | Pursue perfection at the expense of shipping |

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "While I'm here, I'll also..." | Scope creep |
| PR touches 20+ files for a "small fix" | Boy Scout Rule overreach |
| "Let me clean up this whole module" | Delivery blocked by improvement |
| Refactoring unrelated to the task | Unnecessary risk introduction |

### Warning Signs of Overreach

- Scope creep in PRs (unrelated files modified)
- "While I'm here" becoming major work items
- Delivery blocked by improvement work
- Test failures in code unrelated to the original task

## Practical Checklist

Before accepting a "cleanup included" decision as VERIFIED:

- [ ] Cleanup is in files already touched for the task
- [ ] Changes are small, safe, and reversible
- [ ] Delivery timeline is not impacted
- [ ] Unrelated improvements tracked as separate issues

## Related Models

- Chesterton's Fence: understand before changing, even during cleanup
- Technical Debt Quadrant: categorize when to invest vs ship
