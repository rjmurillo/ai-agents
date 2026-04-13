# Gall's Law

**Created**: 2026-01-10
**Category**: Mental Models / System Design

## The Law

"A complex system that works is invariably found to have evolved from a simple system that worked. A complex system designed from scratch never works and cannot be patched up to make it work. You have to start over with a working simple system."

**Attribution**: John Gall, "Systemantics" (1975)

## Core Insight

Build simple working systems first, then iterate. Big bang approaches fail. Incremental evolution succeeds.

## Examples

| Outcome | System | Approach |
|---------|--------|----------|
| Success | World Wide Web | Simple document sharing evolved to complex platform |
| Failure | CORBA | Complex specifications from scratch |

## Application to This Project

**When adding features**:

1. Start with minimal viable implementation
2. Validate with real usage
3. Add complexity only when needed
4. Prefer iteration over comprehensive design

**When designing architecture**:

1. Don't design for all possible futures
2. Build what's needed now
3. Refactor as patterns emerge
4. Trust that you can evolve

## Warning Signs

- Comprehensive frameworks before features
- Building for all possible future requirements
- Complete rewrites instead of evolution

## Relationship to Other Principles

- **YAGNI**: Don't build what's not needed
- **Agile**: Iterate based on feedback
- **Evolutionary Architecture**: Let architecture emerge

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- [yagni-principle](yagni-principle.md): Build only what's needed
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
