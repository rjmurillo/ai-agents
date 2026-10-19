---
source: wiki/concepts/Mental Models/Boy Scout Rule.md
created: 2026-04-11
review-by: 2026-07-11
---

# Boy Scout Rule

> "Always leave the codebase cleaner than you found it."

Attribution: Robert C. Martin (Uncle Bob)

## Core Insight

Make small improvements continuously. Do not wait for dedicated refactoring sprints. Incremental improvement prevents rot. Compounding effect over time.

## Practical Application

| While doing this... | Also do this... |
|---------------------|-----------------|
| Fixing a bug | Rename confusing variable |
| Adding a feature | Extract method for clarity |
| Reading code | Update outdated comment |
| Code review | Suggest small improvement |

## Boundaries

| Do | Don't |
|----|-------|
| Related improvements | Unrelated gold-plating |
| Small, safe changes | Large refactorings |
| Current area of code | Wander through codebase |
| Balance with delivery | Perfect at expense of shipping |

## During Analysis and PR Work

1. Notice small improvements in touched files
2. Include in same PR if related to the change
3. Separate PR if unrelated but valuable
4. Document rationale in commit message

## Warning Signs of Overreach

- Scope creep in PRs
- "While I'm here" becoming major work
- Delivery blocked by improvement

## Using This in Analysis Recommendations

When reporting findings, classify improvements by scope:

| Classification | Action | Example |
|---------------|--------|---------|
| Boy Scout fix | Include with current work | Rename misleading variable |
| Small refactor | Separate PR, same sprint | Extract method from 40-line function |
| Large refactor | Dedicated task with plan | Restructure module boundaries |
| Architecture change | ADR required | Change data flow pattern |

## Related Concepts

- **Chesterton's Fence**: Understand before changing
- **Strangler Fig Pattern**: Incremental migration for larger changes
- **Technical Debt Quadrant**: Categorize when to invest vs ship
