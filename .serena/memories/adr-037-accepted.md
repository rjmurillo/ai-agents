# ADR-037 Memory Router Architecture - Accepted

**Status**: Accepted (2026-01-01)
**Rounds**: 2 (Phase 1 review + revision + Phase 4 convergence)

## Key Decisions

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

- ADR: `.agents/architecture/ADR-037-memory-router-architecture.md`
- Debate Log: `.agents/critique/ADR-037-debate-log.md`
