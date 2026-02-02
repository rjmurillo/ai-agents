# YAGNI (You Aren't Gonna Need It)

**Created**: 2026-01-10
**Category**: Mental Models / Simplicity

## The Principle

Don't add functionality until it is necessary. Speculative generalization wastes effort on features that may never be needed.

**Attribution**: Extreme Programming (XP) community

## Cost of Violation

| Cost Type | Description |
|-----------|-------------|
| Development time | Building unused features |
| Complexity | Code paths for theoretical cases |
| Maintenance | Keeping unused code working |
| Wrong abstractions | Insufficient real-world validation |

## Decision Framework

| Question | If Yes | If No |
|----------|--------|-------|
| Do we need this now? | Build it | Don't build it |
| Are we uncertain? | Build simplest version | Wait |
| Is this speculative? | Don't build it | Build it |

## Application to This Project

**Before adding features**:

1. Is there a current user need?
2. Is there a current PR/issue requiring this?
3. Can we add it later when actually needed?

**Before adding abstraction**:

1. Do we have 3+ concrete cases?
2. Are patterns actually emerging?
3. Or are we imagining future needs?

## Common Violations

- Adding configurability for theoretical variations
- Building frameworks before understanding the domain
- Over-engineering for scale not yet needed
- Adding "nice to have" features during core work

## Trust the Future

- Future requirements will have future context
- Current assumptions may be wrong
- Simpler code is easier to extend later

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- [galls-law](galls-law.md): Start simple, evolve
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
