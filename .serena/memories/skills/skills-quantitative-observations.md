# Skill Sidecar Learnings: Quantitative Analysis

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

None yet.

## Preferences (MED confidence)

### Skill-Quantitative-007: Break-Even Point Modeling for Tiered Architecture
**Pattern**: When evaluating tiered vs consolidated architectures, model cross-over points for query patterns. ADR-017 tiered memory architecture has break-even at 9 skills from same domain. Query requiring 9+ skills from one domain makes consolidated index more efficient (1 read vs 9 index reads). Tiered architecture wins for cross-domain queries.

**Evidence**: Session 83 quantitative analysis (2025-12-23) corrected ADR-017 numerical claims:
- Token reduction: 78% (claimed) → 27.6% uncached or 81.6% cached (actual)
- Efficiency: 2.25x (claimed) → 4.62x cached or 0.48x uncached (actual)
- Critical dependency: MCP caching behavior

**When Applied**: When designing tiered indexing systems, calculate break-even points based on expected query patterns (single-domain vs cross-domain).

**Limitation**: Assumes uniform skill distribution across domains. Real-world skew (e.g., 60% github, 20% issue, 20% pr) shifts break-even point.

**Session**: batch-28, 2026-01-18

---

### Skill-Quantitative-008: File Overhead at Scale for Indexing
**Pattern**: When designing multi-tier indexes, calculate file overhead impact for tooling (git status, CI, file watches). Tiered memory index adds 20% file count overhead at scale.

**Evidence**: Session 83 calculation (2025-12-23) for 1,000 memories:
- Consolidated: 1,001 files (1 index + 1,000 memories)
- Tiered: 1,201 files (1 root + 200 domain indexes @ 5 files each + 1,000 memories)
- Overhead grows with domain count, not memory count

**When Applied**: When evaluating index architecture trade-offs. File overhead may be acceptable if queries reduce from O(n) to O(log n).

**Limitation**: 20% overhead calculation assumes 10 domains with even distribution. Fewer domains or consolidation reduces overhead.

**Session**: batch-28, 2026-01-18

---

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-architecture-index](skills-architecture-index.md)
- [skills-architecture-observations](skills-architecture-observations.md)
- [skills-autonomous-execution-index](skills-autonomous-execution-index.md)
