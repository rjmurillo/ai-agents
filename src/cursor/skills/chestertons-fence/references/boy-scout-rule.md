---
source: wiki/concepts/Mental Models/Boy Scout Rule.md
created: 2026-04-11
review-by: 2026-07-11
---

# Boy Scout Rule

> "Always leave the codebase cleaner than you found it." -- Robert C. Martin

## Core Insight

Make small improvements continuously. Do not wait for dedicated refactoring sprints. Incremental improvement prevents rot.

## Scoped Application

The Boy Scout Rule applies ONLY to code you touch for the current task. Do not expand scope to adjacent code.

| Do | Do Not |
|----|--------|
| Related improvements in touched files | Unrelated gold-plating |
| Small, safe changes | Large refactorings |
| Current area of code | Wandering through codebase |
| Balance with delivery | Perfect at expense of shipping |

## During Investigation

When running a Chesterton's Fence investigation:

1. Keep the investigation read-only; it authorizes no edit
2. Report a confirmed defect you find, with its impact and proof
3. Leave preferences out of the report
4. A later change that acts on the finding applies the limits below

Limits for any change this investigation suggests: see Drive-By Fixes in the `avoiding-manufactured-work` skill.

## Warning Signs of Overreach

- Scope creep in PRs
- "While I'm here" becoming major work
- Delivery blocked by improvement

## Connection to Chesterton's Fence

Understand before changing (Chesterton's Fence). Improve incrementally once understood (Boy Scout Rule). These two models work together: investigate first, then leave it better.
