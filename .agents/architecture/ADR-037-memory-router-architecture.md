# ADR-037: Memory Router Architecture

**Status**: Accepted
**Date**: 2026-01-01
**Revised**: 2026-01-01
**Author**: Session 123 (Phase 2A Memory System)
**Decision**: Unified memory access layer with Serena-first routing, Forgetful augmentation

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
2. **Serena-First Routing**: Serena as canonical layer (per ADR-007), Forgetful as augmentation
3. **Result Augmentation**: Enhance Serena results with Forgetful semantic matches when available
4. **Availability Detection**: Automatic routing based on system health
5. **Cross-Platform Guarantee**: Always works via Serena; Forgetful enhances when present

**Architectural Alignment**: Per ADR-007 (Memory-First Architecture) and memory-architecture-serena-primary, Serena is the canonical memory layer because it travels with the Git repository. Forgetful provides supplementary semantic search but its database contents are local-only and unavailable on hosted platforms.

### Architecture

```text
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
│  │ Serena MCP      │              │ Forgetful MCP   │       │
│  │ (Canonical)     │              │ (Augmentation)  │       │
│  │ File-based      │              │ Port 8020       │       │
│  │                 │              │                 │       │
│  │ ✓ Always avail  │              │ ✓ Semantic      │       │
│  │ ✓ Git-synced    │              │ ✓ Auto-link     │       │
│  │ ✓ 460+ memories │              │ ✓ Embeddings    │       │
│  │ ✓ Lexical match │              │ ✗ Local-only    │       │
│  └─────────────────┘              └─────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Routing Logic

```powershell
function Search-Memory {
    param(
        [ValidatePattern('^[a-zA-Z0-9\s\-.,_()&:]+$')]
        [ValidateLength(1, 500)]
        [string]$Query,

        [ValidateRange(1, 100)]
        [int]$MaxResults = 10,

        [switch]$SemanticOnly,  # Force Forgetful-only (requires availability)
        [switch]$LexicalOnly    # Force Serena-only (always available)
    )

    # 1. ALWAYS query Serena first (canonical layer, per ADR-007)
    $serenaResults = Invoke-SerenaSearch -Query $Query -MaxResults $MaxResults

    # 2. Augment with Forgetful semantic search if available
    if (-not $LexicalOnly) {
        $forgetfulAvailable = Test-ForgetfulAvailable  # Cached 30s TTL
        if ($forgetfulAvailable) {
            $forgetfulResults = Invoke-ForgetfulSearch -Query $Query -MaxResults $MaxResults
            $serenaResults = Merge-MemoryResults `
                -Canonical $serenaResults `
                -Augmentation $forgetfulResults
        }
    }

    # 3. Return Serena results (possibly augmented with Forgetful matches)
    return $serenaResults
}
```

**Key Design Choices**:

1. **Serena always executes first** - Guarantees cross-platform availability
2. **Forgetful augments, never replaces** - Semantic matches enhance but don't override
3. **Input validation** - Prevents injection via ValidatePattern
4. **Cached health check** - 30s TTL prevents per-query latency overhead

### Result Merging Strategy

**Chosen Strategy**: Serena-first with Forgetful augmentation

| Phase | Action | Result |
|-------|--------|--------|
| 1. Canonical | Query Serena (always) | Base result set |
| 2. Augment | Query Forgetful (if available) | Semantic matches |
| 3. Merge | Deduplicate by content hash | Enhanced result set |
| 4. Return | Serena results + unique Forgetful matches | Final results |

**Merge Rules**:

1. **Serena results always included** - They are canonical
2. **Forgetful adds new matches** - Only if not already in Serena results (by hash)
3. **Serena wins on collision** - If same content exists in both, use Serena metadata
4. **Order preserved** - Serena results first, then Forgetful additions

### Deduplication Algorithm

```powershell
function Merge-MemoryResults {
    param(
        [array]$Canonical,      # Serena results (always included)
        [array]$Augmentation    # Forgetful results (additions only)
    )

    # Build hash set of canonical content
    $canonicalHashes = @{}
    foreach ($memory in $Canonical) {
        $hash = Get-ContentHash -Content $memory.Content -Algorithm SHA256
        $canonicalHashes[$hash] = $true
    }

    # Add unique augmentation results
    $merged = [System.Collections.ArrayList]::new($Canonical)
    foreach ($memory in $Augmentation) {
        $hash = Get-ContentHash -Content $memory.Content -Algorithm SHA256
        if (-not $canonicalHashes.ContainsKey($hash)) {
            $null = $merged.Add($memory)
            $canonicalHashes[$hash] = $true  # Prevent duplicates within augmentation
        }
    }

    return $merged
}

function Get-ContentHash {
    param([string]$Content, [string]$Algorithm = 'SHA256')

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
    $hashBytes = [System.Security.Cryptography.HashAlgorithm]::Create($Algorithm).ComputeHash($bytes)
    return [System.BitConverter]::ToString($hashBytes) -replace '-', ''
}
```

**Identity Semantics**: Serena file names (e.g., `powershell-array-handling`) are the canonical IDs. Forgetful observation IDs are local-only and not portable across environments.

### Health Check Specification

```powershell
function Test-ForgetfulAvailable {
    # Use cached result if within TTL
    $cacheKey = 'ForgetfulHealthCheck'
    $cacheTTL = 30  # seconds

    if ($script:HealthCache -and $script:HealthCache.Timestamp -gt (Get-Date).AddSeconds(-$cacheTTL)) {
        return $script:HealthCache.Available
    }

    # TCP connect with 500ms timeout
    $endpoint = Get-ForgetfulEndpoint  # From .mcp.json
    $tcpClient = [System.Net.Sockets.TcpClient]::new()

    try {
        $connectTask = $tcpClient.ConnectAsync($endpoint.Host, $endpoint.Port)
        $completed = $connectTask.Wait(500)  # 500ms timeout

        $available = $completed -and $tcpClient.Connected

        # Cache result
        $script:HealthCache = @{
            Available = $available
            Timestamp = Get-Date
        }

        return $available
    }
    catch {
        $script:HealthCache = @{ Available = $false; Timestamp = Get-Date }
        return $false
    }
    finally {
        $tcpClient.Dispose()
    }
}
```

**Health Check Design**:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Timeout | 500ms | Fast enough for per-session check; slow services fail early |
| Cache TTL | 30s | Balances freshness vs latency overhead |
| Method | TCP connect | Fastest check; HTTP would add 50-100ms |
| Failure mode | Return false | Graceful degradation to Serena-only |

### Interface Specification

```powershell
# Search across all memory systems (Serena-first, Forgetful augmentation)
Search-Memory -Query "PowerShell array handling" -MaxResults 10

# Force lexical-only (Serena, no Forgetful)
Search-Memory -Query "session protocol" -LexicalOnly

# Force semantic-only (Forgetful, requires availability)
Search-Memory -Query "semantic similarity" -SemanticOnly

# Get specific memory by canonical ID (Serena file name)
Get-Memory -Id "powershell-array-handling"

# Save to Serena (canonical) with optional Forgetful sync
Save-Memory -Content "..." -Tags @("powershell", "patterns")

# Check system health
Get-MemoryRouterStatus
# Returns: @{ Serena = $true; Forgetful = $true|$false; CacheAge = [timespan] }
```

---

## Security

### Input Validation

All query inputs are validated before processing:

```powershell
# Query parameter validation
[ValidatePattern('^[a-zA-Z0-9\s\-.,_()&:]+$')]  # Alphanumeric + safe punctuation
[ValidateLength(1, 500)]                         # Reasonable length limits
[string]$Query
```

**Prevented Attack Vectors**:

| Attack | Mitigation | CWE |
|--------|------------|-----|
| Regex injection | ValidatePattern whitelist | CWE-20 |
| Buffer overflow | ValidateLength(1, 500) | CWE-120 |
| Path traversal | No file paths in queries | CWE-22 |
| Command injection | No shell execution | CWE-78 |

### Transport Security

| Connection | Protocol | Security |
|------------|----------|----------|
| Serena MCP | Local file I/O | No network exposure |
| Forgetful MCP | HTTP localhost:8020 | Localhost-only assumption |

**Localhost Assumption**: Forgetful runs on localhost only. If remote deployment is needed in future, HTTPS with TLS verification would be required (not in current scope).

### Data Handling

- **No secrets in queries**: Queries should not contain credentials, API keys, or PII
- **Content hashing**: SHA-256 for deduplication (cryptographically secure)
- **Logging**: Query patterns logged for debugging; content NOT logged

---

## Synchronization Strategy

**Added**: 2026-01-03 (Session 205, Issue #747)

### Problem

Memory Router provides unified search across Serena (canonical) and Forgetful (augmentation), but no mechanism ensures Forgetful stays synchronized with Serena changes.

**Impact without synchronization**:
- Forgetful serves stale content after Serena updates
- Deleted Serena memories remain in Forgetful (orphaned entries)
- Search results show inconsistent content between systems
- Manual database rebuilds required to restore consistency

### Design Decisions

**Serena Remains Canonical** (ADR-037 compliance):
- Serena is Git-synced, always available, travels with repository
- Forgetful is local-only, supplementary semantic search
- All writes go to Serena; Forgetful is read-only from agent perspective

**Synchronization Direction**:
- **Unidirectional**: Serena → Forgetful only
- **Rationale**: Serena is authoritative source per ADR-007
- **Future**: Bidirectional sync (Forgetful annotations → Serena) deferred to Phase 2C

**Deletion Handling**:
- **Soft delete**: Mark Forgetful memories as obsolete (not hard delete)
- **Rationale**: Preserves semantic graph, enables audit trail
- **Implementation**: Set `is_obsolete=true`, `obsolete_reason="Deleted from Serena"`

### Proposed Implementation

**Detailed Plan**: `.agents/planning/phase2b-memory-sync-strategy.md`
**Tracking Issue**: #747

**Hybrid Approach**:

1. **Primary: Git Hook Sync**
   - Trigger: Pre-commit hook detects `.serena/memories/` changes
   - Script: `Sync-MemoryToForgetful.ps1 -Path {file} -Operation {CreateOrUpdate|Delete}`
   - Coverage: Automatic for all committed Serena changes
   - Performance: Target <500ms overhead for 10 memories
   - Failure Mode: Graceful degradation (log warning, allow commit)

2. **Fallback: Manual Sync Command**
   - Trigger: User runs explicit command
   - Script: `Sync-SerenaToForgetful.ps1 -Full` or `-Incremental`
   - Use Case: Recovery from drift, batch sync after git pull
   - Performance: Target <60s for 500 memories

3. **Validation: Freshness Check**
   - Script: `Test-MemoryFreshness.ps1`
   - Output: In-sync, stale, missing, orphaned counts
   - Frequency: On-demand or periodic (CI integration)
   - Performance: Target <10s for 500 memories

### Synchronization Algorithm

**Content-Hash Based Deduplication**:

```powershell
function Sync-MemoryToForgetful {
    param([string]$Path, [string]$Operation)

    # 1. Check Forgetful availability (graceful degradation)
    if (-not (Test-ForgetfulAvailable)) {
        Write-Warning "Forgetful unavailable, skipping sync"
        return  # Non-blocking
    }

    # 2. For creates/updates
    if ($Operation -eq 'CreateOrUpdate') {
        $content = Get-Content -Path $Path -Raw
        $newHash = Get-ContentHash -Content $content -Algorithm SHA256

        # 3. Query existing Forgetful entry
        $existing = Find-ForgetfulMemoryByTitle -Title $memoryName

        # 4. Skip if content unchanged (optimization)
        if ($existing -and (Get-ContentHash $existing.content) -eq $newHash) {
            return  # Already in sync
        }

        # 5. Create or update
        if ($existing) {
            Update-ForgetfulMemory -Id $existing.id -Content $content
        } else {
            Create-ForgetfulMemory -Content $content
        }
    }

    # 6. For deletes
    if ($Operation -eq 'Delete') {
        $existing = Find-ForgetfulMemoryByTitle -Title $memoryName
        if ($existing) {
            Update-ForgetfulMemory -Id $existing.id `
                -IsObsolete $true `
                -ObsoleteReason "Deleted from Serena canonical source"
        }
    }
}
```

**Key Properties**:
- **Idempotent**: Running sync multiple times produces same result
- **Non-blocking**: Failures don't prevent commits
- **Incremental**: Only syncs changed memories
- **Verifiable**: Hash comparison proves consistency

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sync coverage | 100% of Serena changes | % commits with successful sync |
| Drift rate | <1% of memories | Freshness check stale count |
| Sync latency | <5s per memory | Hook execution time |
| Manual sync time | <60s for 500 memories | Full sync runtime |
| Freshness check | <10s | Validation script runtime |

### Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Hook adds commit latency | Medium | Batch processing, timeout after 5s, skip if slow |
| Forgetful down during sync | Low | Graceful degradation, log warning |
| Metadata parsing fails | Medium | Default values, Pester test coverage |
| Hash collision (SHA-256) | Critical (Very Low) | Use full SHA-256 (not truncated) |
| Orphaned entries accumulate | Low | Periodic cleanup via Test-MemoryFreshness |

### Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Planning | ✅ COMPLETE | `.agents/planning/phase2b-memory-sync-strategy.md` |
| Core Scripts | ✅ COMPLETE | `scripts/memory_sync/` (Python + MCP subprocess) |
| Git Hook | ✅ COMPLETE | `.githooks/pre-commit` queue-based integration |
| Manual Sync | ✅ COMPLETE | `python -m memory_sync sync` / `sync-batch` CLI |
| Validation | ✅ COMPLETE | `python -m memory_sync validate` freshness report |
| ADR Update | ✅ COMPLETE | Implementation status updated |

**Implementation Details**:

- **Approach**: Python + MCP subprocess (JSON-RPC 2.0 over stdio)
- **MCP Command**: `uvx forgetful-ai` spawned as subprocess
- **Sync Direction**: Unidirectional (Serena -> Forgetful)
- **State Tracking**: `.memory_sync_state.json` maps memory names to Forgetful IDs + content hashes
- **Hook Behavior**: Queue-based by default (<10ms), optional immediate sync with `MEMORY_SYNC_IMMEDIATE=1`
- **Graceful Degradation**: Hook never blocks commits, CLI reports failures with ADR-035 exit codes

**Related**:
- **Issue #747**: Serena-Forgetful Memory Synchronization
- **PR #746**: M-009 Bootstrap + Memory Sync Strategy
- **Planning**: `.agents/planning/phase2b-memory-sync-strategy.md`

---

## Consequences

### Positive

1. **Simplified Agent Logic**: Agents call `Search-Memory` without system awareness
2. **Cross-Platform Guarantee**: Always works via Serena (Git-synced, travels with repo)
3. **Enhanced Results**: Semantic augmentation when Forgetful available
4. **Future-Proof**: Can add more memory backends without changing agent code
5. **ADR-007 Compliant**: Serena-first routing respects canonical layer decision

### Negative

1. **Additional Layer**: One more module to maintain (~300 lines estimated)
2. **Latency Overhead**: Health check (cached) + routing adds ~10-50ms
3. **Complexity**: Deduplication logic required for cross-system merge

### Neutral

1. **Configuration**: Memory Router reads `.mcp.json` for Forgetful endpoint
2. **Logging**: Routes decisions logged for debugging (query patterns, not content)

### Confirmation

To verify this decision is correctly implemented:

1. **Unit tests**: Each function has Pester tests with ≥80% coverage
2. **Integration tests**: Serena-only, Forgetful-only, and combined scenarios
3. **Performance tests**: Measure routing overhead vs baseline (target: <50ms)
4. **Cross-platform test**: Verify Serena-only mode works when Forgetful unavailable

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

**Status**: Baseline measured; targets pending M-008 validation

| Metric | Baseline (Serena) | Target (Router) | Status |
|--------|-------------------|-----------------|--------|
| Search latency | 530ms (measured) | ≤580ms (Serena + overhead) | Pending M-008 |
| Augmented latency | N/A | ≤630ms (Serena + Forgetful) | Pending M-008 |
| Health check overhead | N/A | <10ms (cached) | Pending M-008 |
| Availability | 100% | 100% (Serena always available) | By design |
| Result relevance | Keyword match | Semantic augmentation | Qualitative |

**Notes**:

1. **Serena-first means no latency improvement** - Router adds overhead, doesn't reduce baseline
2. **Forgetful augmentation adds latency** - Semantic search is additive, not replacement
3. **M-008 benchmark required** - Measure actual Forgetful query latency before finalizing targets

**Acceptance Criteria** (from M-008):

- Router overhead < 50ms when Forgetful available
- Router overhead < 20ms when Forgetful unavailable (cached health check)
- Total latency < 700ms for augmented searches

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
| Architect | ACCEPT | 2026-01-01 | All P0 concerns resolved |
| Critic | ACCEPT | 2026-01-01 | Sufficient detail for implementation |
| Independent-Thinker | ACCEPT | 2026-01-01 | ADR-007 alignment verified |
| Security | ACCEPT | 2026-01-01 | Risk score 3/10 (Low) |
| Analyst | D&C | 2026-01-01 | Performance unvalidated; M-008 will validate |
| High-Level-Advisor | ACCEPT | 2026-01-01 | Proceed to implementation |

**Consensus**: 5 Accept + 1 Disagree-and-Commit = ACCEPTED (Round 2)

---

## Revision History

### v2.0 (2026-01-01) - Major Revision

Addressed all P0 blocking issues from Round 1 adr-review:

| Issue | Resolution | Section |
|-------|------------|---------|
| Contradicts ADR-007 | Inverted to Serena-first routing | Decision, Architecture |
| Deduplication undefined | Added SHA-256 algorithm with pseudocode | Deduplication Algorithm |
| Query injection risk | Added ValidatePattern input validation | Security |
| Health check undefined | Added TCP connect with 500ms timeout, 30s cache | Health Check Specification |
| Performance unvalidated | Marked targets as "Pending M-008" | Performance Targets |
| Identity semantics unclear | Declared Serena file names as canonical IDs | Deduplication Algorithm |
| Result merging undefined | Chose "Serena-first with augmentation" | Result Merging Strategy |

**Debate Log**: `.agents/critique/ADR-037-debate-log.md`

### v1.0 (2026-01-01) - Initial Proposal

- Status: Needs-Revision (6 agents blocked)
- Key finding: Routing logic contradicted ADR-007 (Serena-first requirement)
