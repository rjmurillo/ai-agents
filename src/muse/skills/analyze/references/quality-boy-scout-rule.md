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
| Fixing a bug | Fix a typo or dead local in the function you edit |
| Adding a feature | Clarify a local name in the function you edit |
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
2. Include in the same PR only as a tidy fix in the function you edit, or as work the change needs
3. Separate branch and PR only for a confirmed defect with a named impact and its own proof; never for a preference
4. Document rationale in commit message

The `avoiding-manufactured-work` skill's Drive-By Fixes section is the canonical limit for this rule.

## Warning Signs of Overreach

- Scope creep in PRs
- "While I'm here" becoming major work
- Delivery blocked by improvement

## Using This in Analysis Recommendations

When reporting findings, classify improvements by scope:

| Classification | Action | Example |
|---------------|--------|---------|
| Boy Scout fix | Include with current work | Rename misleading variable |
| Refactor the change needs | Same PR, as part of the change | Extract a method the new code calls |
| Large refactor | Dedicated task with plan | Restructure module boundaries |
| Architecture change | ADR required | Change data flow pattern |

## Related Concepts

- **Chesterton's Fence**: Understand before changing
- **Strangler Fig Pattern**: Incremental migration for larger changes
- **Technical Debt Quadrant**: Categorize when to invest vs ship
