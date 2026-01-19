# PRD: Memory Enhancement Layer for Serena + Forgetful

**Status**: Draft
**Author**: Claude
**Created**: 2026-01-19
**Updated**: 2026-01-19
**Related Issues**: #724 (Traceability Graph), #584 (Serena Integration)
**Inspiration**: [GitHub Copilot Agentic Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)

---

## 1. Problem Statement

### 1.1 Current State

We have a working memory system:

| Component | Role | Status |
|-----------|------|--------|
| **Serena** | Canonical markdown storage (`.serena/memories/`) | ✅ 460+ memories |
| **Forgetful** | Semantic vector search | ✅ Configured |
| **MemoryRouter** | Unified search across both | ✅ ADR-037 |

### 1.2 What's Missing

GitHub Copilot's memory system revealed capabilities we lack:

| Capability | GitHub Copilot | Our System |
|------------|----------------|------------|
| **Citation validation** | Memories reference `file:line`, verified at retrieval | ❌ No citations |
| **Staleness detection** | Stale memories auto-flagged when code changes | ❌ Manual curation only |
| **Just-in-time verification** | Verify on read, not continuous sync | ❌ No verification |
| **Confidence scoring** | Track memory reliability over time | ❌ No scoring |
| **Graph traversal** | Navigate memory relationships | ⚠️ Links exist, no traversal tools |

### 1.3 Opportunity

**Enhance Serena + Forgetful** with citation validation and graph operations—don't replace them.

This delivers 90% of GitHub Copilot's value at 10% of the cost.

---

## 2. Goals and Non-Goals

### 2.1 Goals

| Priority | Goal | Success Metric |
|----------|------|----------------|
| P0 | **Citation schema for Serena memories** | Standardized frontmatter format |
| P0 | **Just-in-time citation verification** | `Verify-MemoryCitations.ps1` script |
| P1 | **Staleness detection in CI** | Pre-commit hook flags stale memories |
| P1 | **Graph traversal on Serena links** | Navigate memory relationships |
| P2 | **Confidence scoring** | Track verification history |
| P2 | **Multi-agent reinforcement** | Agents validate each other's memories |

### 2.2 Non-Goals

| Explicitly Out of Scope | Rationale |
|------------------------|-----------|
| Replace Serena | Already works, 460+ memories invested |
| Replace Forgetful | Already provides semantic search |
| New storage format | Serena markdown is fine |
| New MCP server | Adds complexity without benefit |
| Standalone operation without Serena | Not needed for this project |

### 2.3 Design Principle

> **Enhance, don't replace.** Every new capability should work WITH the existing Serena + Forgetful stack, not around it.

---

## 3. User Stories

### 3.1 Core Personas

| Persona | Description |
|---------|-------------|
| **Agent** | AI coding assistant using Serena for memory |
| **Developer** | Human who reviews/curates memories |
| **CI Pipeline** | Validates memory integrity on PR |

### 3.2 User Stories

#### US-1: Agent Saves Memory with Citations (P0)

**As an** agent that discovered a pattern,
**I want to** save it with references to specific code locations,
**So that** the memory can be validated against code changes.

**Acceptance Criteria:**
- [ ] Citation schema defined in Serena memory frontmatter
- [ ] `mcp__serena__write_memory` accepts citation metadata
- [ ] Citations include path, line number, and snippet

#### US-2: Agent Verifies Memory Before Acting (P0)

**As an** agent retrieving a memory,
**I want to** verify its citations still match the codebase,
**So that** I don't act on stale information.

**Acceptance Criteria:**
- [ ] Verification checks file:line exists
- [ ] Verification checks snippet content matches
- [ ] Stale citations return specific mismatch details
- [ ] Agent receives confidence score

#### US-3: CI Detects Stale Memories (P1)

**As a** CI pipeline,
**I want to** validate all memory citations on PR,
**So that** stale memories are flagged before merge.

**Acceptance Criteria:**
- [ ] Batch validation script for all Serena memories
- [ ] Exit code reflects validation status
- [ ] Report lists stale citations with details
- [ ] Integrates with existing pre-commit hooks

#### US-4: Agent Traverses Memory Graph (P1)

**As an** agent investigating a topic,
**I want to** follow links between related Serena memories,
**So that** I can build comprehensive understanding.

**Acceptance Criteria:**
- [ ] Graph traversal works on existing Serena link format
- [ ] Supports BFS/DFS with configurable depth
- [ ] Returns adjacency structure
- [ ] Uses `mcp__serena__*` tools, not custom storage

#### US-5: Developer Sees Memory Health Dashboard (P2)

**As a** developer,
**I want to** see which memories are stale or low-confidence,
**So that** I can prioritize curation efforts.

**Acceptance Criteria:**
- [ ] Script generates memory health report
- [ ] Shows last verified date per memory
- [ ] Ranks by staleness / confidence
- [ ] Outputs markdown for easy review

---

## 4. Technical Design

### 4.1 Citation Schema (Serena Memory Extension)

Extend existing Serena memory format with optional `citations` block:

```markdown
# .serena/memories/api-versioning.md (existing format)

This is the existing memory content...

## Citations

| File | Line | Snippet | Verified |
|------|------|---------|----------|
| src/client/constants.ts | 42 | `API_VERSION = 'v2'` | 2026-01-18 |
| server/routes/api.ts | 15 | `router.use('/v2'` | 2026-01-18 |

## Metadata

- **Confidence**: 0.92
- **Last Verified**: 2026-01-18T10:30:00Z
- **Links**: api-deployment-checklist, client-sdk-patterns
```

**Why table format?**
- Human-readable (grep/cat friendly)
- Parseable with simple regex
- No YAML frontmatter changes needed
- Backwards compatible with existing memories

### 4.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Enhancement Layer (NEW)                           │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐    │
│  │ Verify-Memory  │  │ Traverse-Graph │  │ Get-MemoryHealth   │    │
│  │ Citations.ps1  │  │ .ps1           │  │ Report.ps1         │    │
│  └───────┬────────┘  └───────┬────────┘  └─────────┬──────────┘    │
│          │                   │                      │               │
└──────────┼───────────────────┼──────────────────────┼───────────────┘
           │                   │                      │
           ▼                   ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Existing Stack (UNCHANGED)                        │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                    MemoryRouter.psm1                        │     │
│  │                    (ADR-037)                                │     │
│  └────────────────────────┬───────────────────────────────────┘     │
│                           │                                          │
│           ┌───────────────┴───────────────┐                         │
│           ▼                               ▼                         │
│  ┌─────────────────┐             ┌─────────────────┐                │
│  │ Serena MCP      │             │ Forgetful MCP   │                │
│  │ (Canonical)     │             │ (Semantic)      │                │
│  │ .serena/memories│             │ Vector search   │                │
│  └─────────────────┘             └─────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 New Scripts

| Script | Purpose | Inputs | Outputs |
|--------|---------|--------|---------|
| `Verify-MemoryCitations.ps1` | Validate citations in a memory | Memory path or ID | Verification result |
| `Invoke-MemoryGraphTraversal.ps1` | BFS/DFS on memory links | Root ID, depth | Adjacency dict |
| `Get-MemoryHealthReport.ps1` | Batch health check | Directory | Markdown report |
| `Add-MemoryCitation.ps1` | Add citation to memory | Memory ID, file, line | Updated memory |

### 4.4 Verification Algorithm

```powershell
function Test-Citation {
    param(
        [string]$Path,
        [int]$Line,
        [string]$Snippet
    )

    # Check file exists
    if (-not (Test-Path $Path)) {
        return @{ Valid = $false; Reason = "File not found" }
    }

    # Check line exists
    $lines = Get-Content $Path
    if ($Line -gt $lines.Count) {
        return @{ Valid = $false; Reason = "Line $Line exceeds file length" }
    }

    # Check snippet matches (fuzzy - contains)
    $actualLine = $lines[$Line - 1]
    if ($actualLine -notmatch [regex]::Escape($Snippet)) {
        return @{
            Valid = $false
            Reason = "Snippet mismatch"
            Expected = $Snippet
            Actual = $actualLine.Trim()
        }
    }

    return @{ Valid = $true }
}
```

### 4.5 Graph Traversal

Serena memories already support links via content references. Parse and traverse:

```powershell
function Get-MemoryLinks {
    param([string]$MemoryPath)

    $content = Get-Content $MemoryPath -Raw

    # Extract from ## Links section or inline references
    $links = @()

    # Pattern 1: ## Links section with bullet list
    if ($content -match '## Links\s*\n((?:[-*]\s+.+\n?)+)') {
        $linkSection = $Matches[1]
        $links += [regex]::Matches($linkSection, '[-*]\s+(\S+)') |
            ForEach-Object { $_.Groups[1].Value }
    }

    # Pattern 2: [[wiki-style]] links
    $links += [regex]::Matches($content, '\[\[([^\]]+)\]\]') |
        ForEach-Object { $_.Groups[1].Value }

    return $links | Select-Object -Unique
}

function Invoke-GraphTraversal {
    param(
        [string]$RootId,
        [int]$MaxDepth = 3,
        [string]$MemoriesPath = ".serena/memories"
    )

    $visited = @{}
    $queue = [System.Collections.Queue]::new()
    $queue.Enqueue(@{ Id = $RootId; Depth = 0 })
    $graph = @{}

    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()

        if ($visited.ContainsKey($current.Id) -or $current.Depth -gt $MaxDepth) {
            continue
        }

        $visited[$current.Id] = $true
        $memoryPath = Join-Path $MemoriesPath "$($current.Id).md"

        if (Test-Path $memoryPath) {
            $links = Get-MemoryLinks -MemoryPath $memoryPath
            $graph[$current.Id] = $links

            foreach ($link in $links) {
                if (-not $visited.ContainsKey($link)) {
                    $queue.Enqueue(@{ Id = $link; Depth = $current.Depth + 1 })
                }
            }
        }
    }

    return $graph
}
```

---

## 5. Integration Points

### 5.1 With Existing MemoryRouter (ADR-037)

```powershell
# Enhanced Search-Memory with verification
function Search-Memory {
    param(
        [string]$Query,
        [switch]$VerifyCitations  # NEW parameter
    )

    # Existing search logic...
    $results = Invoke-SerenaSearch -Query $Query

    if ($VerifyCitations) {
        $results = $results | ForEach-Object {
            $verification = Verify-MemoryCitations -MemoryPath $_.Path
            $_ | Add-Member -NotePropertyName 'CitationsValid' -NotePropertyValue $verification.Valid
            $_ | Add-Member -NotePropertyName 'Confidence' -NotePropertyValue $verification.Confidence
            $_
        } | Where-Object { $_.CitationsValid -or -not $_.HasCitations }
    }

    return $results
}
```

### 5.2 With Session Protocol

Add to session start (optional gate):

```markdown
## Session Start (Enhanced)

1. ✅ Activate Serena
2. ✅ Read HANDOFF.md
3. ✅ Create session log
4. ✅ Read usage-mandatory memory
5. ✅ Verify branch
6. **NEW (optional)**: Run `Get-MemoryHealthReport.ps1` for relevant memories
```

### 5.3 With CI/Pre-commit

```yaml
# .github/workflows/memory-validation.yml
name: Memory Validation

on:
  pull_request:
    paths:
      - '.serena/memories/**'
      - 'src/**'  # Code changes may invalidate citations

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate memory citations
        run: pwsh scripts/Verify-AllMemoryCitations.ps1
        continue-on-error: true  # Warning, not blocking initially
```

---

## 6. Implementation Phases

### Phase 1: Citation Schema & Verification (1 week)

**Deliverables:**
- [ ] Document citation schema (table format in memory body)
- [ ] `Verify-MemoryCitations.ps1` - single memory verification
- [ ] `Verify-AllMemoryCitations.ps1` - batch verification
- [ ] Unit tests for verification logic

**Exit Criteria:**
- Can verify citations in any Serena memory
- Clear pass/fail with details on mismatches

### Phase 2: Graph Traversal (1 week)

**Deliverables:**
- [ ] `Get-MemoryLinks.ps1` - extract links from memory
- [ ] `Invoke-MemoryGraphTraversal.ps1` - BFS/DFS traversal
- [ ] Integration with existing link formats
- [ ] Cycle detection

**Exit Criteria:**
- Can traverse memory relationships
- Works with existing Serena memory format

### Phase 3: Health Reporting & CI Integration (1 week)

**Deliverables:**
- [ ] `Get-MemoryHealthReport.ps1` - batch health check
- [ ] CI workflow for PR validation
- [ ] Pre-commit hook (optional)
- [ ] Documentation for adding citations to memories

**Exit Criteria:**
- CI flags stale memories on code changes
- Developers can see memory health at a glance

### Phase 4: Confidence Scoring & Tooling (1 week)

**Deliverables:**
- [ ] Confidence calculation based on verification history
- [ ] `Add-MemoryCitation.ps1` - helper to add citations
- [ ] Integration with `reflect` skill for auto-citations
- [ ] Memory health dashboard

**Exit Criteria:**
- Memories track confidence over time
- Easy to add/update citations

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Citation coverage | 20% of high-value memories | Memories with ≥1 citation |
| Stale detection accuracy | >90% | True positives on known stale |
| CI integration | Active on all PRs | Workflow runs |
| Graph traversal performance | <500ms for depth 3 | Benchmark |
| Developer adoption | Citations added to new memories | PR reviews |

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Citation schema too complex | Medium | Medium | Use simple table format, not YAML |
| False positives (valid code flagged stale) | Medium | High | Fuzzy matching; snippet tolerance |
| Performance on large memory sets | Low | Medium | Lazy loading; caching |
| Adoption friction | Medium | Medium | Make citations optional; demonstrate value |
| Breaking existing memories | Low | High | Backwards compatible schema |

---

## 9. Open Questions

1. **Citation granularity**: File-level vs line-level vs function-level?
   - Recommendation: Line-level with fuzzy snippet matching

2. **Verification trigger**: On every read vs on-demand vs scheduled?
   - Recommendation: On-demand with CI batch validation

3. **Stale memory handling**: Warning vs blocking vs auto-archive?
   - Recommendation: Warning initially, blocking after adoption

4. **Serena schema extension**: Table in body vs YAML frontmatter?
   - Recommendation: Table in body (backwards compatible, human-readable)

---

## 10. Appendix

### A. Example Memory with Citations

```markdown
# API Version Synchronization

Client SDK API_VERSION constant must exactly match server route prefix.

## Why This Matters

Discovered during incident on 2026-01-10 when client was updated to v2
but server routes still used v1 prefix. All API calls returned 404.

## Action

When updating API version:
1. Search for `API_VERSION` in client code
2. Search for route prefix in server code
3. Update both in the same commit

## Citations

| File | Line | Snippet | Verified |
|------|------|---------|----------|
| src/client/constants.ts | 42 | `API_VERSION = 'v2'` | 2026-01-18 |
| server/routes/api.ts | 15 | `router.use('/v2'` | 2026-01-18 |

## Links

- api-deployment-checklist
- client-sdk-patterns

## Metadata

- **Confidence**: 0.92
- **Last Verified**: 2026-01-18T10:30:00Z
```

### B. Comparison: Enhancement vs Replacement

| Aspect | This PRD (Enhancement) | Original PRD (Replacement) |
|--------|------------------------|---------------------------|
| Storage | Serena (existing) | New markdown store |
| Semantic search | Forgetful (existing) | Chroma (new) |
| Effort | ~4 weeks | ~8 weeks |
| Risk | Low (additive) | High (migration) |
| Value delivered | Citations + Graph | Same |
| Dependencies | None new | chromadb, PyYAML |

### C. References

- [GitHub Copilot Agentic Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)
- [Issue #724: Traceability Graph Implementation](https://github.com/rjmurillo/ai-agents/issues/724)
- [ADR-007: Memory-First Architecture](/.agents/architecture/ADR-007-memory-first-architecture.md)
- [ADR-037: Memory Router Architecture](/.agents/architecture/ADR-037-memory-router-architecture.md)
- [Serena MCP Documentation](https://github.com/oraios/serena)
