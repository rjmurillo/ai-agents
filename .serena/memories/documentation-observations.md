# Skill Observations: documentation

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 2

## Purpose

This memory captures learnings from using documentation organization and naming patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Analysis/research files belong in .agents/analysis/, not with implementation code (Session 2026-01-14, 2026-01-14)
- File names must be 3-5 words kebab-case, descriptive for scanning/recall (Session 2026-01-14, 2026-01-14)
- ADR documentation should use dedicated subsections for new content types, not add to existing sections (Session 2026-01-16-session-07, 2026-01-16)
- Verify example paths in comments match actual repository structure - outdated examples mislead maintainers (Session 2026-01-16-session-07, 2026-01-16)
- Code duplication should be consolidated proactively - combine identical case branches to reduce maintenance burden (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Analysis files use {session}-{3-5-word-description}.md format for traceability (Session 2026-01-14, 2026-01-14)
- Distinguish .agents/critique/ (plan reviews) from .agents/analysis/ (research) (Session 2026-01-14, 2026-01-14)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Remove duplicate configuration entries immediately - they suggest copy-paste errors (Session 2026-01-16-session-07, 2026-01-16)
- Don't remove template variables without understanding full usage context - external tools may depend on them (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-14 | 2026-01-14 | HIGH | Analysis files belong in .agents/analysis/ not with code |
| 2026-01-14 | 2026-01-14 | HIGH | File names must be 3-5 words kebab-case descriptive |
| 2026-01-14 | 2026-01-14 | MED | Analysis files use {session}-{description}.md format |
| 2026-01-14 | 2026-01-14 | MED | Distinguish critique/ (reviews) from analysis/ (research) |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | ADR documentation should use dedicated subsections |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Verify example paths in comments match repository structure |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Code duplication should be consolidated proactively |
| 2026-01-16 | 2026-01-16-session-07 | MED | Remove duplicate configuration entries immediately |
| 2026-01-16 | 2026-01-16-session-07 | MED | Don't remove template variables without verification |

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)