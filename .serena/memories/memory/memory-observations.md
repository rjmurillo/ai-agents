# Skill Observations: memory

**Last Updated**: 2026-01-17
**Sessions Analyzed**: 6

## Purpose

This memory captures learnings from using the `memory` skill across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Analyze .claude-mem backup files for real user patterns when improving heuristics (Session 2026-01-13-session-906, 2026-01-13)
- Show quantitative improvements (5.5x, 10x) with before/after metrics (Session 2026-01-13-session-906, 2026-01-13)
- Authoritative consolidation pattern: Create single comprehensive source of truth rather than maintaining fragmented knowledge across multiple locations - eliminates inconsistency and reduces maintenance burden (Session 819, 2026-01-10)
  - Evidence: Engineering knowledge integration - consolidated 67 memories with clear taxonomy (Foundational 0-5y, Principal 15+y, Distinguished 25+y)
- Memory obsolescence pattern: Mark outdated memories as obsolete with superseded_by links to replacement - preserves history while preventing stale information usage (Session 819, 2026-01-10)
- Engineering knowledge organization by experience level: Separate foundational (0-5y), principal (15+y), and distinguished (25+y) knowledge for targeted retrieval (Sessions 813, 816, 817, 2026-01-10)
- Duplicate "## Related" sections in memory files cause Validate-MemoryIndex.ps1 failures - maintain single Related section at end of file (Session 908, 2026-01-14)
  - Evidence: skills-*-index memories had duplicate Related blocks after merge, causing validation to fail when updating Serena context
- Atomic memories with domain index pattern: Create individual memory files for each concept, then update domain index for discoverability - enables targeted retrieval while maintaining overview (Session 814, 2026-01-10)
  - Evidence: Created 12 atomic concept memories (CAP theorem, resilience patterns, C4 model, etc.) + updated foundational-knowledge-index

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-13 | 2026-01-13-session-906 | MED | Analyze .claude-mem backup files for real user patterns |
| 2026-01-13 | 2026-01-13-session-906 | MED | Show quantitative improvements with before/after metrics |
| 2026-01-10 | Session 819 | MED | Authoritative consolidation eliminates fragmented knowledge |
| 2026-01-10 | Session 819 | MED | Mark obsolete memories with superseded_by links |
| 2026-01-10 | Sessions 813, 816, 817 | MED | Organize engineering knowledge by experience level |
| 2026-01-14 | Session 908 | MED | Duplicate Related sections cause validation failures |
| 2026-01-10 | Session 814 | MED | Atomic memories with domain index for knowledge organization |

## Related

- [memory-001-feedback-retrieval](memory-001-feedback-retrieval.md)
- [memory-architecture-serena-primary](memory-architecture-serena-primary.md)
- [memory-index](memory-index.md)
- [memory-size-001-decomposition-thresholds](memory-size-001-decomposition-thresholds.md)
- [memory-system-fragmentation-tech-debt](memory-system-fragmentation-tech-debt.md)
