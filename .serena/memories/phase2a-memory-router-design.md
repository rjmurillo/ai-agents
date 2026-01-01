# Phase 2A Memory Router Design

**Session**: 123
**Date**: 2026-01-01
**ADR**: ADR-037

## Key Decisions

1. **Unified Interface**: Single `Search-Memory` entry point for all memory operations
2. **Fallback Chain**: Forgetful (primary) → Serena (fallback) with graceful degradation
3. **Result Merging**: Primary-first when good results, union when sparse

## Architecture

```
Memory Router
    │
    ├── Forgetful MCP (Primary)
    │   - Semantic search via embeddings
    │   - Port 8020
    │   - 96-164x faster target
    │
    └── Serena MCP (Fallback)
        - Lexical search via keywords
        - Port 24282
        - ~530ms baseline
```

## Benchmark Baseline

- Serena: ~530ms average for 8 queries across 460 files
- Forgetful: TBD (service availability varies)

## Implementation Status

| Component | Status |
|-----------|--------|
| ADR-037 | Proposed |
| Benchmark script | Complete |
| Router module | Not started |
| Agent integration | Not started |

## Related

- ADR-007: Memory-First Architecture
- ADR-017: Tiered Memory Index
- Issue #167: Vector Memory System
- Analysis: 123-phase2a-memory-architecture-review.md
