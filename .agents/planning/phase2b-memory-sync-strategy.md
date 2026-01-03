# Phase 2B: Serena-Forgetful Synchronization Strategy

**Status**: Proposed
**Date**: 2026-01-03
**Phase**: 2B (Graph Performance Optimization)
**Related**: ADR-037 (Memory Router Architecture), M-009 (Bootstrap)

---

## Problem Statement

The ai-agents memory system uses two complementary backends (ADR-037):

- **Serena** (canonical): Git-synced, file-based, always available (`.serena/memories/*.md`)
- **Forgetful** (augmentation): Local-only, semantic search, knowledge graph (SQLite + vector DB)

**Current State**: No documented mechanism to keep Forgetful synchronized with Serena changes.

**Impact**:
- Forgetful serves stale results after Serena updates
- Deleted Serena memories remain in Forgetful (orphaned entries)
- Search results show inconsistent content between systems
- Manual Forgetful database rebuilds required to restore consistency

**Gap Identified**: Session 205 (M-009 Bootstrap completion)

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority | Rationale |
|----|-------------|----------|-----------|
| F-001 | Detect Serena changes (create/update/delete) | P0 | Core sync trigger |
| F-002 | Propagate creates to Forgetful | P0 | Keep coverage complete |
| F-003 | Propagate updates to Forgetful | P0 | Prevent stale content |
| F-004 | Propagate deletes to Forgetful | P1 | Prevent orphaned entries |
| F-005 | Validate Forgetful freshness | P1 | Detect drift |
| F-006 | Manual sync command | P1 | Recovery mechanism |
| F-007 | Batch sync for efficiency | P2 | Reduce overhead |

### Non-Functional Requirements

| ID | Requirement | Target | Measurement |
|----|-------------|--------|-------------|
| NF-001 | Sync latency | <5s for single memory | Time from Serena write to Forgetful update |
| NF-002 | Batch sync latency | <60s for 100 memories | Full sync operation time |
| NF-003 | Drift detection | <10s | Freshness validation script runtime |
| NF-004 | Git hook overhead | <500ms | Pre-commit hook execution time |
| NF-005 | Availability | Graceful degradation | System works if sync fails |

---

## Design Alternatives

### Alternative 1: Git Hook Sync (RECOMMENDED)

**Trigger**: Pre-commit hook detects Serena memory changes

**Flow**:
```bash
# .git/hooks/pre-commit
git diff --cached --name-only | grep "^.serena/memories/" | while read file; do
    if [ -f "$file" ]; then
        # Create or update in Forgetful
        pwsh .claude/skills/memory/scripts/Sync-MemoryToForgetful.ps1 -Path "$file" -Operation CreateOrUpdate
    else
        # Delete from Forgetful
        pwsh .claude/skills/memory/scripts/Sync-MemoryToForgetful.ps1 -Path "$file" -Operation Delete
    fi
done
```

**Pros**:
- Automatic, no manual intervention
- Runs at natural sync point (commit)
- Catches all Serena changes
- Low cognitive overhead for developers

**Cons**:
- Adds latency to commit (mitigated by batch processing)
- Requires Forgetful running (mitigated by graceful degradation)
- More complex hook implementation

**Risk Mitigation**:
- Timeout after 5s per memory
- Skip sync if Forgetful unavailable (log warning)
- Batch multiple changes for efficiency

### Alternative 2: Manual Sync Command

**Trigger**: User runs explicit sync command

**Flow**:
```powershell
# Manual full sync
Sync-SerenaToForgetful -Full

# Manual incremental sync (since last sync)
Sync-SerenaToForgetful -Incremental
```

**Pros**:
- Simple implementation
- No commit latency impact
- User controls when sync happens

**Cons**:
- Easy to forget (drift accumulates)
- Requires discipline
- No automatic coverage

**Use Case**: Recovery mechanism, not primary strategy

### Alternative 3: Scheduled Sync (Background Job)

**Trigger**: Cron/scheduled task runs periodically

**Flow**:
```bash
# Run every 5 minutes via systemd timer or cron
*/5 * * * * pwsh /path/to/Sync-SerenaToForgetful.ps1 -Incremental
```

**Pros**:
- No commit latency
- Automatic coverage
- Works for long-running development sessions

**Cons**:
- Delay between change and sync (up to interval)
- Requires system-level configuration
- Platform-specific (systemd vs cron vs Task Scheduler)

### Alternative 4: Event-Driven Sync (Filesystem Watcher)

**Trigger**: Filesystem watcher detects `.serena/memories/` changes

**Flow**:
```powershell
# Background process watching .serena/memories/
$watcher = New-FileSystemWatcher -Path ".serena/memories" -Filter "*.md"
Register-ObjectEvent $watcher "Created" -Action { Sync-MemoryToForgetful }
Register-ObjectEvent $watcher "Changed" -Action { Sync-MemoryToForgetful }
Register-ObjectEvent $watcher "Deleted" -Action { Sync-MemoryToForgetful }
```

**Pros**:
- Near-instant sync
- No commit latency
- Catches all changes (even non-committed)

**Cons**:
- Requires background process (complex lifecycle)
- Platform-specific APIs
- Noise from editor autosaves
- Reliability concerns (process crashes)

---

## Recommended Approach: Hybrid Strategy

**Primary**: Git Hook Sync (Alternative 1)
**Fallback**: Manual Sync Command (Alternative 2)
**Validation**: Freshness Check Script

### Phase 1: Git Hook Implementation

**Script**: `.claude/skills/memory/scripts/Sync-MemoryToForgetful.ps1`

```powershell
<#
.SYNOPSIS
    Synchronize Serena memory to Forgetful MCP.

.PARAMETER Path
    Path to Serena memory file (relative to repo root).

.PARAMETER Operation
    Sync operation: CreateOrUpdate, Delete.

.PARAMETER Force
    Force sync even if content hash matches (skip optimization).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Path,

    [Parameter(Mandatory)]
    [ValidateSet('CreateOrUpdate', 'Delete')]
    [string]$Operation,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# 1. Check Forgetful availability
if (-not (Test-ForgetfulAvailable)) {
    Write-Warning "Forgetful unavailable, skipping sync for $Path"
    exit 0  # Graceful degradation
}

# 2. Extract memory name from path
$memoryName = [System.IO.Path]::GetFileNameWithoutExtension($Path)

if ($Operation -eq 'Delete') {
    # 3a. Find Forgetful memory by title matching filename
    $memories = mcp__forgetful__execute_forgetful_tool("query_memory", @{
        query = $memoryName
        query_context = "Finding memory to delete during sync"
        k = 1
    })

    if ($memories.primary_memories.Count -gt 0) {
        $forgetfulId = $memories.primary_memories[0].id
        mcp__forgetful__execute_forgetful_tool("update_memory", @{
            memory_id = $forgetfulId
            is_obsolete = $true
            obsolete_reason = "Deleted from Serena canonical source"
        })
        Write-Verbose "Marked Forgetful memory $forgetfulId as obsolete (Serena source deleted)"
    }
    exit 0
}

# 3b. Read Serena content
$content = Get-Content -Path $Path -Raw

# 4. Compute content hash for deduplication
$hash = Get-ContentHash -Content $content -Algorithm SHA256

# 5. Check if Forgetful already has this content (skip if unchanged)
if (-not $Force) {
    $existing = mcp__forgetful__execute_forgetful_tool("query_memory", @{
        query = $memoryName
        query_context = "Checking for existing memory during sync"
        k = 1
    })

    if ($existing.primary_memories.Count -gt 0) {
        $existingHash = Get-ContentHash -Content $existing.primary_memories[0].content
        if ($existingHash -eq $hash) {
            Write-Verbose "Forgetful already has current content for $memoryName (hash match), skipping"
            exit 0
        }
    }
}

# 6. Parse frontmatter for metadata
$frontmatter = Parse-MemoryFrontmatter -Content $content

# 7. Create or update in Forgetful
$memoryData = @{
    title = $frontmatter.title ?? $memoryName
    content = $content -replace '^---.*?---\r?\n', ''  # Strip frontmatter
    context = "Synced from Serena canonical source at $Path"
    keywords = $frontmatter.keywords ?? @($memoryName)
    tags = $frontmatter.tags ?? @("serena-sync")
    importance = $frontmatter.importance ?? 7
    project_ids = @(1)  # ai-agents project
}

# Check if exists for update vs create
$existing = mcp__forgetful__execute_forgetful_tool("query_memory", @{
    query = $memoryName
    query_context = "Finding memory for update during sync"
    k = 1
})

if ($existing.primary_memories.Count -gt 0) {
    # Update existing
    $forgetfulId = $existing.primary_memories[0].id
    mcp__forgetful__execute_forgetful_tool("update_memory", ($memoryData + @{ memory_id = $forgetfulId }))
    Write-Verbose "Updated Forgetful memory $forgetfulId from Serena $Path"
} else {
    # Create new
    mcp__forgetful__execute_forgetful_tool("create_memory", $memoryData)
    Write-Verbose "Created Forgetful memory from Serena $Path"
}

exit 0
```

**Helper Function**:
```powershell
function Parse-MemoryFrontmatter {
    param([string]$Content)

    if ($Content -notmatch '^---\r?\n(.*?)\r?\n---') {
        return @{}
    }

    $yaml = $matches[1]
    $metadata = @{}

    # Simple YAML parsing (keywords, tags, importance)
    if ($yaml -match 'keywords:\s*\[(.*?)\]') {
        $metadata.keywords = @($matches[1] -split ',' | ForEach-Object { $_.Trim().Trim('"').Trim("'") })
    }
    if ($yaml -match 'tags:\s*\[(.*?)\]') {
        $metadata.tags = @($matches[1] -split ',' | ForEach-Object { $_.Trim().Trim('"').Trim("'") })
    }
    if ($yaml -match 'importance:\s*(\d+)') {
        $metadata.importance = [int]$matches[1]
    }
    if ($yaml -match 'title:\s*(.+)') {
        $metadata.title = $matches[1].Trim().Trim('"').Trim("'")
    }

    return $metadata
}
```

**Git Hook**: `.git/hooks/pre-commit` (or `.claude/hooks/pre-commit.ps1` for Claude Code integration)

```bash
#!/bin/bash
# Sync Serena memory changes to Forgetful before commit

# Get staged Serena memory files
staged_memories=$(git diff --cached --name-only --diff-filter=ACM | grep '^\.serena/memories/.*\.md$')
deleted_memories=$(git diff --cached --name-only --diff-filter=D | grep '^\.serena/memories/.*\.md$')

# Sync creates/updates
for file in $staged_memories; do
    pwsh -NoProfile .claude/skills/memory/scripts/Sync-MemoryToForgetful.ps1 \
        -Path "$file" -Operation CreateOrUpdate
done

# Sync deletes
for file in $deleted_memories; do
    pwsh -NoProfile .claude/skills/memory/scripts/Sync-MemoryToForgetful.ps1 \
        -Path "$file" -Operation Delete
done

exit 0  # Always succeed (graceful degradation)
```

### Phase 2: Manual Sync Command

**Script**: `.claude/skills/memory/scripts/Sync-SerenaToForgetful.ps1`

```powershell
<#
.SYNOPSIS
    Manual sync of Serena memories to Forgetful.

.PARAMETER Full
    Full sync (all memories).

.PARAMETER Incremental
    Incremental sync (only changed since last sync).

.PARAMETER DryRun
    Show what would be synced without making changes.
#>
[CmdletBinding()]
param(
    [Parameter(ParameterSetName='Full')]
    [switch]$Full,

    [Parameter(ParameterSetName='Incremental')]
    [switch]$Incremental,

    [Parameter()]
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Get all Serena memories
$serenaPath = ".serena/memories"
$memories = Get-ChildItem -Path $serenaPath -Filter "*.md"

$syncCount = 0
$skipCount = 0
$errorCount = 0

foreach ($file in $memories) {
    try {
        if ($DryRun) {
            Write-Host "Would sync: $($file.Name)"
        } else {
            & .claude/skills/memory/scripts/Sync-MemoryToForgetful.ps1 `
                -Path $file.FullName -Operation CreateOrUpdate -Verbose
        }
        $syncCount++
    } catch {
        Write-Warning "Failed to sync $($file.Name): $_"
        $errorCount++
    }
}

Write-Host "`nSync Summary:"
Write-Host "  Synced: $syncCount"
Write-Host "  Errors: $errorCount"
```

### Phase 3: Freshness Validation

**Script**: `.claude/skills/memory/scripts/Test-MemoryFreshness.ps1`

```powershell
<#
.SYNOPSIS
    Validate Forgetful freshness against Serena canonical source.

.OUTPUTS
    PSCustomObject with drift statistics.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-ForgetfulAvailable)) {
    Write-Warning "Forgetful unavailable, cannot check freshness"
    return @{ Status = "Unavailable" }
}

$serenaPath = ".serena/memories"
$serenaMemories = Get-ChildItem -Path $serenaPath -Filter "*.md"

$stats = @{
    Total = $serenaMemories.Count
    InSync = 0
    Stale = 0
    Missing = 0
    Orphaned = 0
    StaleMemories = @()
    MissingMemories = @()
}

foreach ($file in $serenaMemories) {
    $memoryName = $file.BaseName
    $serenaContent = Get-Content -Path $file.FullName -Raw
    $serenaHash = Get-ContentHash -Content $serenaContent

    # Query Forgetful for this memory
    $forgetful = mcp__forgetful__execute_forgetful_tool("query_memory", @{
        query = $memoryName
        query_context = "Freshness validation"
        k = 1
    })

    if ($forgetful.primary_memories.Count -eq 0) {
        $stats.Missing++
        $stats.MissingMemories += $memoryName
        continue
    }

    $forgetfulContent = $forgetful.primary_memories[0].content
    $forgetfulHash = Get-ContentHash -Content $forgetfulContent

    if ($serenaHash -eq $forgetfulHash) {
        $stats.InSync++
    } else {
        $stats.Stale++
        $stats.StaleMemories += $memoryName
    }
}

# Check for orphaned Forgetful memories
$allForgetful = mcp__forgetful__execute_forgetful_tool("list_memories", @{ project_ids = @(1) })
$serenaNames = @($serenaMemories | ForEach-Object { $_.BaseName })

foreach ($forgetfulMemory in $allForgetful.memories) {
    if ($forgetfulMemory.title -notin $serenaNames) {
        $stats.Orphaned++
    }
}

return [PSCustomObject]$stats
```

---

## Implementation Plan

### Milestone 1: Core Sync Scripts (Week 1)

**Tasks**:
- [ ] S-001: Create `Sync-MemoryToForgetful.ps1` with CreateOrUpdate/Delete operations
- [ ] S-002: Create `Parse-MemoryFrontmatter` helper function
- [ ] S-003: Add Pester tests for sync script (mock Forgetful calls)
- [ ] S-004: Test with sample memories (create, update, delete scenarios)

**Acceptance Criteria**:
- Script syncs creates correctly
- Script syncs updates correctly
- Script marks deletes as obsolete in Forgetful
- Script gracefully degrades if Forgetful unavailable
- Test coverage ≥80%

### Milestone 2: Git Hook Integration (Week 2)

**Tasks**:
- [ ] H-001: Create pre-commit hook script
- [ ] H-002: Test hook with staged memory changes
- [ ] H-003: Measure hook overhead (target: <500ms for 10 memories)
- [ ] H-004: Document hook installation in CONTRIBUTING.md

**Acceptance Criteria**:
- Hook detects staged Serena changes
- Hook calls sync script for each change
- Hook completes in <500ms for typical commits
- Hook gracefully degrades if sync fails

### Milestone 3: Manual Sync Command (Week 2)

**Tasks**:
- [ ] M-001: Create `Sync-SerenaToForgetful.ps1` wrapper
- [ ] M-002: Add -Full and -Incremental modes
- [ ] M-003: Add -DryRun for safety
- [ ] M-004: Create skill wrapper for user-facing command

**Acceptance Criteria**:
- Full sync processes all Serena memories
- Incremental sync only processes changed files
- DryRun shows what would be synced
- Progress reporting for long operations

### Milestone 4: Freshness Validation (Week 3)

**Tasks**:
- [ ] V-001: Create `Test-MemoryFreshness.ps1` script
- [ ] V-002: Report in-sync, stale, missing, orphaned counts
- [ ] V-003: Add to session protocol (recommended check)
- [ ] V-004: Document remediation steps

**Acceptance Criteria**:
- Script detects stale Forgetful entries
- Script detects missing Forgetful entries
- Script detects orphaned Forgetful entries
- Script completes in <10s for 500 memories

### Milestone 5: ADR Update (Week 3)

**Tasks**:
- [ ] A-001: Add "Synchronization Strategy" section to ADR-037
- [ ] A-002: Trigger adr-review for updated ADR
- [ ] A-003: Address review feedback
- [ ] A-004: Get consensus (6 agents accept or disagree-and-commit)

**Acceptance Criteria**:
- ADR-037 documents sync strategy
- All P0 concerns from review addressed
- Consensus achieved (6/6 accept or D&C)

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sync coverage | 100% of Serena changes | % of commits with successful sync |
| Drift rate | <1% of memories | Test-MemoryFreshness.ps1 stale count |
| Sync latency | <5s per memory | Hook execution time |
| Manual sync time | <60s for 500 memories | Full sync script runtime |
| Freshness check time | <10s | Test-MemoryFreshness.ps1 runtime |

---

## Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Hook adds commit latency | Medium | High | Batch processing, timeout, skip if slow |
| Forgetful down during sync | Low | Medium | Graceful degradation, log warning |
| Metadata parsing fails | Medium | Low | Default values, validate with tests |
| Hash collision (SHA-256) | Critical | Very Low | Use full SHA-256 (not truncated) |
| Orphaned entries accumulate | Low | Medium | Periodic manual cleanup via Test-MemoryFreshness |

---

## Future Enhancements

**Phase 2C: Advanced Sync**
- Bidirectional sync (Forgetful → Serena for annotations)
- Conflict resolution UI
- Sync status dashboard

**Phase 3: Performance**
- Parallel sync for batch operations
- Incremental sync via git diff comparison
- Caching layer for hash computations

**Phase 4: Monitoring**
- Prometheus metrics for sync operations
- Alerting on high drift rates
- Sync audit log

---

## Related

- **ADR-037**: Memory Router Architecture
- **M-009**: Bootstrap ai-agents Project into Memory System
- **Issue**: TBD (to be created)
- **PR**: TBD (this document will be in PR)

---

## Approval

**Planner**: Proposed (this document)
**Critic**: Pending review
**Architect**: Pending review
**High-Level-Advisor**: Pending review
