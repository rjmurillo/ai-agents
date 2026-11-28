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

| While doing this... | What fits the Drive-By Fixes classes |
|---------------------|-----------------|
| Fixing a bug | Optional tidy fix: remove a dead local from code you edit |
| Adding a feature | Optional tidy fix: clarify a misleading local name in code you edit |
| Reading code | Report a confirmed defect; leave taste alone |
| Code review | Flag scope creep; do not ask for cleanup the change does not need |

## Boundaries

| Do | Don't |
|----|-------|
| Related improvements | Unrelated gold-plating |
| Small, safe changes | Large refactorings |
| Current area of code | Wander through codebase |
| Balance with delivery | Perfect at expense of shipping |

## During Analysis and PR Work

1. Notice small improvements in touched files
2. Include in the same PR only as a tidy fix in code you edit, or as work the change needs
3. Separate branch and PR only for a confirmed defect with a named impact, its own proof, and authority for that PR; never for a preference
4. Name each tidy fix in the PR body

The `avoiding-manufactured-work` skill's Drive-By Fixes section is the canonical limit for this rule.

## Warning Signs of Overreach

- Scope creep in PRs
- "While I'm here" becoming major work
- Delivery blocked by improvement

## Using This in Analysis Recommendations

When reporting findings, classify improvements by scope:

| Classification | Action | Example |
|---------------|--------|---------|
| Tidy fix | Optional; same PR, own commit, named in its body | Fix a typo in code you edit |
| Refactor the change needs | Same PR, as part of the change | Extract a method the new code calls |
| Large refactor the change does not need | Do not do it; it is class 4 taste | Restructure module boundaries |
| Architecture change | ADR required | Change data flow pattern |

## Related Concepts

- **Chesterton's Fence**: Understand before changing
- **Strangler Fig Pattern**: Incremental migration for larger changes
- **Technical Debt Quadrant**: Categorize when to invest vs ship
