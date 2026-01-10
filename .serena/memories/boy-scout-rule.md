# Boy Scout Rule

**Created**: 2026-01-10
**Category**: Mental Models / Continuous Improvement

## The Rule

"Always leave the codebase cleaner than you found it."

**Attribution**: Robert C. Martin (Uncle Bob)

## Core Insight

Make small improvements continuously. Don't wait for dedicated refactoring sprints. Incremental improvement prevents rot.

## Practical Examples

| While doing this... | Also do this... |
|---------------------|-----------------|
| Fixing a bug | Rename confusing variable |
| Adding feature | Extract method for clarity |
| Reading code | Update outdated comment |
| Code review | Suggest small improvement |

## Boundaries

| Do | Don't |
|----|-------|
| Related improvements | Unrelated gold-plating |
| Small, safe changes | Large refactorings |
| Current area of code | Wandering through codebase |
| Balance with delivery | Perfect at expense of shipping |

## Application to This Project

**During PR work**:

1. Notice small improvements in touched files
2. Include in same PR if related
3. Separate PR if unrelated but valuable
4. Document rationale in commit message

**Session protocol**:

1. Run markdownlint (automated cleanup)
2. Update outdated comments noticed during work
3. Fix minor issues in files you touch

## Warning Signs of Overreach

- Scope creep in PRs
- "While I'm here" becoming major work
- Delivery blocked by improvement

## The Balance

Clean code is a journey, not a destination. Each session leaves things slightly better. Compounding effect over time.

## Related

- `foundational-knowledge-index`: Overview
- Refactoring practices
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
