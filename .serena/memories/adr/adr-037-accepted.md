# ADR-037 Memory Router Architecture - Superseded by ADR-106

**Status**: SUPERSEDED (2026-09-09) by
`.agents/architecture/ADR-106-serena-only-memory-architecture.md`. Recorded as
Accepted on 2026-01-01; that is history, not current state.
**Rounds**: 2 (Phase 1 review + revision + Phase 4 convergence)

## Current truth, read this before the record below

Serena is the only memory backend. The supplementary store this ADR routed to
was decommissioned under issue #5574, so the two-backend router it specifies no
longer describes anything that runs. Decisions 2, 3 and 4 below are withdrawn:
there is no second store to augment from, nothing to deduplicate against, and
no backend to health-check. Decision 1 survives in the weaker form that Serena
executes, because it is the only thing to execute.

The episode tier is NOT part of this withdrawal. It is governed by ADR-038 and
is still read on every search, at
`.claude/skills/memory/scripts/search_memory.py:296`.

Cite ADR-106 for memory architecture. Do not cite this file as current.

## Key Decisions (historical, as accepted on 2026-01-01)

1. **Serena-first routing** - Per ADR-007, Serena always executes first
2. **Forgetful augmentation** - Enhances but never replaces Serena results
3. **SHA-256 deduplication** - Content hashing with Serena-wins on collision
4. **500ms health check** - TCP connect timeout, 30s cache TTL

## Agent Consensus

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |
| independent-thinker | Accept |
| security | Accept |
| analyst | Disagree-and-Commit |
| high-level-advisor | Accept |

## Dissent Tracked

Analyst: Performance targets unvalidated. M-008 benchmark required before Phase 2.

## Next Steps

- M-003: Implement MemoryRouter.psm1
- M-008: Benchmark Forgetful latency (must complete before Phase 2)
- Issue #731: Update agent prompts to use Memory Router

## References

- Successor ADR: `.agents/architecture/ADR-106-serena-only-memory-architecture.md`
- ADR: `.agents/architecture/ADR-037-memory-router-architecture.md`
- Debate Log: `.agents/critique/ADR-037-debate-log.md`

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)
