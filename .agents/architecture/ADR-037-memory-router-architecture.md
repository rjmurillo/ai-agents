# ADR-037: Memory Router Architecture

**Status**: Needs-Revision
**Date**: 2026-01-01
**Author**: Session 123 (Phase 2A Memory System)
**Decision**: Unified memory access layer integrating Serena and Forgetful

---

## Context

The ai-agents system currently has two memory subsystems with different capabilities:

| System | Type | Strengths | Weaknesses |
|--------|------|-----------|------------|
| **Serena** | File-based (`.serena/memories/`) | 460+ memories, always available, lexical search | O(n) scan, keyword-only, ~530ms average |
| **Forgetful** | Vector database (HTTP MCP) | Semantic search, auto-linking, embeddings | Requires running service, newer system |

ADR-007 (Memory-First Architecture) mandates memory retrieval before reasoning. ADR-017 (Tiered Memory Index) optimizes Serena's lexical approach. Phase 2A M-003 requires integration between these systems.

### Problem Statement

Agents must currently:

1. Know which memory system to query for each use case
2. Handle Forgetful unavailability gracefully
3. Merge results from multiple systems
4. Avoid duplicate queries across systems

This cognitive overhead violates the memory-first principle by making retrieval complex.

---

## Decision

Implement a **Memory Router** that provides:

1. **Unified Interface**: Single entry point for all memory operations
2. **Fallback Chain**: Forgetful → Serena with graceful degradation
3. **Result Merging**: Deduplicate and rank results from multiple sources
4. **Availability Detection**: Automatic routing based on system health

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Memory Router                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Search-Memory -Query "pattern" -MaxResults 10       │    │
│  │ Get-Memory -Id "memory-id"                          │    │
│  │ Save-Memory -Content "..." -Tags @("...")           │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                 │
│           ┌────────────────┴────────────────┐               │
│           ▼                                 ▼               │
│  ┌─────────────────┐              ┌─────────────────┐       │
│  │ Forgetful MCP   │              │ Serena MCP      │       │
│  │ (Primary)       │              │ (Fallback)      │       │
│  │ Port 8020       │              │ Port 24282      │       │
│  │                 │              │                 │       │
│  │ ✓ Semantic      │              │ ✓ Always avail  │       │
│  │ ✓ Auto-link     │              │ ✓ 460+ memories │       │
│  │ ✓ Embeddings    │              │ ✓ Lexical match │       │
│  └─────────────────┘              └─────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Routing Logic

```powershell
function Search-Memory {
    param(
        [string]$Query,
        [int]$MaxResults = 10,
        [switch]$ForceSerena,
        [switch]$ForceForgetful
    )

    # 1. Check Forgetful availability
    $forgetfulAvailable = Test-ForgetfulAvailable

    # 2. Primary search (Forgetful if available)
    $results = @()
    if (-not $ForceSerena -and $forgetfulAvailable) {
        $results = Invoke-ForgetfulSearch -Query $Query -Limit $MaxResults
    }

    # 3. Fallback to Serena if needed
    if ($results.Count -eq 0 -or $ForceSerena) {
        $serenaResults = Invoke-SerenaSearch -Query $Query -Limit $MaxResults
        $results = Merge-MemoryResults -Primary $results -Secondary $serenaResults
    }

    return $results
}
```

### Result Merging Strategy

| Strategy | When to Use | Behavior |
|----------|-------------|----------|
| **Primary-first** | Forgetful available, good results | Return Forgetful results, skip Serena |
| **Union** | Forgetful unavailable or sparse | Combine both, deduplicate by content hash |
| **Weighted** | Both return results | Score by semantic similarity + recency |

### Interface Specification

```powershell
# Search across all memory systems
Search-Memory -Query "PowerShell array handling" -MaxResults 10

# Force specific system
Search-Memory -Query "session protocol" -ForceSerena
Search-Memory -Query "semantic similarity" -ForceForgetful

# Get specific memory by ID
Get-Memory -Id "powershell-array-handling" -System Serena
Get-Memory -Id "abc123" -System Forgetful

# Save to primary (Forgetful with Serena backup)
Save-Memory -Content "..." -Tags @("powershell", "patterns")

# Check system health
Get-MemoryRouterStatus
```

---

## Consequences

### Positive

1. **Simplified Agent Logic**: Agents call `Search-Memory` without system awareness
2. **Graceful Degradation**: Works with Serena-only when Forgetful unavailable
3. **Best-of-Both**: Semantic search when available, lexical fallback always works
4. **Future-Proof**: Can add more memory backends without changing agent code

### Negative

1. **Additional Layer**: One more module to maintain
2. **Latency Overhead**: Health check + routing adds ~10-50ms
3. **Result Deduplication**: Need content hashing for cross-system dedup

### Neutral

1. **Configuration**: Memory Router needs `.mcp.json` for endpoint discovery
2. **Logging**: Should log routing decisions for debugging

---

## Implementation Plan

### Phase 1: Core Module (M-003)

1. Create `scripts/MemoryRouter.psm1` with:
   - `Test-ForgetfulAvailable`
   - `Invoke-ForgetfulSearch`
   - `Invoke-SerenaSearch`
   - `Merge-MemoryResults`
   - `Search-Memory` (main entry point)

2. Create `tests/MemoryRouter.Tests.ps1` with:
   - Unit tests for each function
   - Integration tests with mock servers
   - Fallback scenario tests

### Phase 2: Agent Integration

1. Update agent prompts to use Memory Router
2. Add Memory Router to SESSION-PROTOCOL
3. Create migration guide for existing memory calls

### Phase 3: Optimization

1. Add result caching (session-local, 5-minute TTL)
2. Implement weighted result merging
3. Add metrics collection for routing decisions

---

## Alternatives Considered

### 1. Forgetful-Only

**Rejected**: Forgetful requires running service; Serena always available.

### 2. Serena-Only (with Embedding Enhancement)

**Rejected**: Would require embedding model in PowerShell; Forgetful already provides.

### 3. Dual-Query Always

**Rejected**: Wastes resources when single system sufficient.

---

## Performance Targets

| Metric | Baseline (Serena) | Target (Router) |
|--------|-------------------|-----------------|
| Search latency | 530ms | 50-100ms (Forgetful primary) |
| Fallback latency | N/A | 550ms (Serena after Forgetful timeout) |
| Availability | 100% | 100% (graceful degradation) |
| Result relevance | Keyword match | Semantic + keyword |

---

## Related

- **ADR-007**: Memory-First Architecture (mandates retrieval before reasoning)
- **ADR-017**: Tiered Memory Index Architecture (Serena optimization)
- **Issue #167**: Vector Memory System
- **Analysis**: `.agents/analysis/123-phase2a-memory-architecture-review.md`
- **Benchmark**: `scripts/Measure-MemoryPerformance.ps1`

---

## Review

| Reviewer | Status | Date | Notes |
|----------|--------|------|-------|
| Architect | BLOCK | 2026-01-01 | 4 P0 gaps: dedup algorithm, identity semantics, routing logic, health check |
| Critic | BLOCK | 2026-01-01 | Failure modes undefined, query injection risk |
| Independent-Thinker | BLOCK | 2026-01-01 | **Contradicts ADR-007** - must invert to Serena-first |
| Security | BLOCK | 2026-01-01 | P1: Input validation missing (CWE-20), HTTP unencrypted (CWE-319) |
| Analyst | CONDITIONAL | 2026-01-01 | Performance targets unvalidated, M-008 incomplete |
| High-Level-Advisor | CONDITIONAL | 2026-01-01 | Complete M-008 benchmarks before implementation |

---

## Required Changes (from adr-review)

**Debate Log**: `.agents/critique/ADR-037-debate-log.md`

### P0 (Blocking)

1. **Invert routing logic**: Serena-first, Forgetful-supplementary (per ADR-007)
2. **Specify deduplication**: SHA-256 content hash, Serena-wins on collision
3. **Add Security section**: Input validation (`ValidatePattern`), localhost assumption
4. **Define health check**: TCP connect, 500ms timeout, 30s TTL cache
5. **Validate performance**: Complete M-008 benchmarks before finalizing targets

### P1 (Important)

6. Choose result merging strategy: "Primary-first with augmentation"
7. Declare Serena file names as canonical IDs
8. Extract Implementation Plan to separate planning document

### Consensus

- Problem statement is valid (6/6 agree)
- Fallback design approach is sound (6/6 agree)
- Unified interface simplifies agent logic (6/6 agree)
