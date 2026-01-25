# Skill Observations: documentation

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 6

## Purpose

This memory captures learnings from documentation standards, maintenance, and quality patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Use full paths (e.g., `scripts/Validate-SessionJson.ps1`) not relative paths in documentation for clarity and direct invocation (Session 2026-01-16-session-07, 2026-01-16)
- Follow-up issue creation for deferred concerns - when ADR debate results in DISAGREE AND COMMIT with P0 concern, create explicit follow-up issue to track resolution (Session 826, 2026-01-13)
  - Evidence: Independent-thinker raised P0 concern about CRLF line endings during ADR-040 amendment debate, deferred to issue #896 for investigation
- Comprehensive documentation suite pattern for feature rollouts - create user guide, architecture doc, ADR, and rollout checklist for significant features (Session 382, 2026-01-16)
  - Evidence: CodeQL integration - created codeql-integration.md (user guide), codeql-architecture.md (design), ADR-041 (decision record), codeql-rollout-checklist.md (deployment validation), updated AGENTS.md with commands section
- Research consolidation pattern - consolidate external documentation with project-specific requirements for new developer onboarding instead of standalone guides (Session 819, 2026-01-10)
  - Evidence: GitHub keywords research - created comprehensive guide covering GitHub keywords, Conventional Commits, and PR etiquette integrated with ADR-005, ADR-006, and usage-mandatory constraints
- Document purpose drift detection - identify when documents evolve beyond original intent (routing-index becomes comprehensive reference) (Session 02, PR #871, 2026-01-11)
  - Evidence: .gemini/styleguide.md grew from routing-index (183 lines) to comprehensive reference (491 lines), refactored back to routing-index pattern to reduce token bloat
- Research documentation pattern - create comprehensive main document + atomic memories for individual concepts + domain index for discoverability (Session 813, 2026-01-10)
  - Evidence: Foundational engineering knowledge - created 3500-word foundational-engineering-knowledge.md, extracted 8 atomic Serena memories (Hyrum's Law, Conway's Law, etc.), created foundational-knowledge-index for central navigation
- ADR implementation notes belong in dedicated Implementation Notes subsection, not Confirmation section (Session 03, 2026-01-16)
  - Evidence: Batch 36 - Moved implementation details from Confirmation to new Implementation Notes subsection for clarity

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | MED | Use full paths not relative paths in documentation |
| 2026-01-13 | Session 826 | MED | Follow-up issue creation for deferred P0 concerns |
| 2026-01-16 | Session 382 | MED | Comprehensive documentation suite pattern for feature rollouts |
| 2026-01-10 | Session 819 | MED | Research consolidation with project-specific integration |
| 2026-01-11 | Session 02, PR #871 | MED | Document purpose drift detection |
| 2026-01-10 | Session 813 | MED | Research documentation pattern with atomic memories |
| 2026-01-16 | Session 03 | MED | ADR implementation notes in dedicated subsection |

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
- [documentation-007-self-contained-artifacts](documentation-007-self-contained-artifacts.md)
- [documentation-008-framework-constraints](documentation-008-framework-constraints.md)
- [documentation-index-selection-decision-tree](documentation-index-selection-decision-tree.md)
- [documentation-observations](documentation-observations.md)
- [documentation-user-facing](documentation-user-facing.md)
- [documentation-verification-protocol](documentation-verification-protocol.md)
