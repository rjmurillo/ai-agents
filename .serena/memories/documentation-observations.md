# Skill Observations: documentation

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 5

## Purpose

This memory captures learnings from using documentation organization and naming patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Analysis/research files belong in .agents/analysis/, not with implementation code (Session 2026-01-14, 2026-01-14)
- File names must be 3-5 words kebab-case, descriptive for scanning/recall (Session 2026-01-14, 2026-01-14)
- ADR documentation should use dedicated subsections for new content types, not add to existing sections (Session 2026-01-16-session-07, 2026-01-16)
- Verify example paths in comments match actual repository structure - outdated examples mislead maintainers (Session 2026-01-16-session-07, 2026-01-16)
- Code duplication should be consolidated proactively - combine identical case branches to reduce maintenance burden (Session 2026-01-16-session-07, 2026-01-16)
- Use Mermaid diagrams instead of ASCII art for governance documentation - improves maintainability (Session 2026-01-16-session-07, PR #715)
- Exclude internal PR/Issue/Session references from src/ and templates/ directories (user-facing content restriction policy) (Session 07, 2026-01-16)
  - Evidence: PR #212 user policy request - 6 files updated to remove internal references like "PR #XX", "Issue #XX", "Session XX", ".agents/", ".serena/" paths, 92% atomicity
- Convert absolute paths to repository-relative before document finalization - environment-specific paths leak into version control (Session 07, 2026-01-16)
  - Evidence: PR #43 - CodeRabbit flagged absolute Windows paths (D:\src\GitHub\...) in References section, tooling limitation/agent gap

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Analysis files use {session}-{3-5-word-description}.md format for traceability (Session 2026-01-14, 2026-01-14)
- Distinguish .agents/critique/ (plan reviews) from .agents/analysis/ (research) (Session 2026-01-14, 2026-01-14)
- Document constraints at point of enforcement, not buried in ADR amendments - improves discoverability for maintainers (Session 2026-01-16-session-07, 2026-01-16)
- Define schema grammar formats explicitly before coding (e.g., [A-Z]+-[A-Z0-9]+) - prevents ambiguity in validation logic (Session 2026-01-16-session-07, PR #715)
- Document runtime limitations in comments near validation code (e.g., 'Cannot validate at parse time due to...') - prevents false optimization attempts (Session 2026-01-16-session-07, PR #715)
- Cross-document data requires automated validation - estimates, dates, cross-refs across planning/critique/implementation (Session 07, 2026-01-16)
  - Evidence: PR #43 - 7 CodeRabbit issues, 4 were cross-document consistency gaps (effort estimates, QA conditions, escalation prompts)

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
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Use Mermaid diagrams instead of ASCII art for governance docs |
| 2026-01-16 | Session 07 | HIGH | Exclude internal PR/Issue/Session references from user-facing content |
| 2026-01-16 | Session 07 | HIGH | Convert absolute paths to repository-relative before finalization |
| 2026-01-16 | 2026-01-16-session-07 | MED | Document constraints at point of enforcement for discoverability |
| 2026-01-16 | 2026-01-16-session-07 | MED | Remove duplicate configuration entries immediately |
| 2026-01-16 | 2026-01-16-session-07 | MED | Don't remove template variables without verification |
| 2026-01-16 | 2026-01-16-session-07 | MED | Define schema grammar formats explicitly before coding |
| 2026-01-16 | 2026-01-16-session-07 | MED | Document runtime limitations near validation code |
| 2026-01-16 | Session 07 | MED | Cross-document data requires automated validation |

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
