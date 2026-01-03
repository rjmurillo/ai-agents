---
name: memory
description: Unified four-tier memory system for AI agents. Tier 1 Semantic (Serena+Forgetful search), Tier 2 Episodic (session replay), Tier 3 Causal (decision patterns). Enables memory-first architecture per ADR-007.
metadata:
  version: 0.2.0
  adr: ADR-037, ADR-038
  timelessness: 8/10
---

# Memory System Skill

Unified memory operations across four tiers for AI agents.

---

## Quick Start

```powershell
# Check system health
pwsh .claude/skills/memory/scripts/Test-MemoryHealth.ps1

# Search memory (Tier 1)
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks"

# Extract episode from session (Tier 2)
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 -SessionLogPath ".agents/sessions/2026-01-01-session-126.md"

# Update causal graph (Tier 3)
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1
```

---

## Triggers

| Trigger Phrase | Maps To |
|----------------|---------|
| "search memory for X" | Tier 1: Search-Memory.ps1 |
| "what do we know about X" | Tier 1: Search-Memory.ps1 |
| "extract episode from session" | Tier 2: Extract-SessionEpisode.ps1 |
| "get episode for session X" | Tier 2: Get-Episode -SessionId "X" |
| "what happened in session X" | Tier 2: Get-Episode -SessionId "X" |
| "find sessions with failures" | Tier 2: Get-Episodes -Outcome "failure" |
| "update causal graph" | Tier 3: Update-CausalGraph.ps1 |
| "what patterns led to success" | Tier 3: Get-Patterns |
| "why did X lead to Y" | Tier 3: Get-CausalPath |
| "check memory health" | Test-MemoryHealth.ps1 |

---

## Quick Reference

| Operation | Type | Name | Key Parameters |
|-----------|------|------|----------------|
| Search facts/patterns | Script | `Search-Memory.ps1` | `-Query`, `-LexicalOnly`, `-MaxResults` |
| Get single session | Function | `Get-Episode` | `-SessionId` |
| Find multiple sessions | Function | `Get-Episodes` | `-Outcome`, `-Task`, `-Since`, `-MaxResults` |
| Trace causation | Function | `Get-CausalPath` | `-FromLabel`, `-ToLabel`, `-MaxDepth` |
| Find success patterns | Function | `Get-Patterns` | `-MinSuccessRate`, `-PatternType` |
| Extract episode | Script | `Extract-SessionEpisode.ps1` | `-SessionLogPath`, `-OutputPath` |
| Update patterns | Script | `Update-CausalGraph.ps1` | `-EpisodePath`, `-DryRun` |
| Health check | Script | `Test-MemoryHealth.ps1` | `-Format` (Json/Table) |
| Benchmark | Script | `Measure-MemoryPerformance.ps1` | `-Iterations`, `-IncludeForgetful` |

---

## Decision Tree: Which Tier?

```text
What do you need?
│
├─► Current facts, patterns, or rules?
│   └─► TIER 1: Search-Memory.ps1
│       │
│       ├─ Forgetful available? → Default (unified search)
│       └─ Forgetful unavailable? → -LexicalOnly (Serena fallback)
│
├─► What happened in a specific session?
│   └─► TIER 2: Get-Episode -SessionId "..."
│
├─► Recent sessions with specific outcome?
│   └─► TIER 2: Get-Episodes -Outcome "failure" -Since 7days
│
├─► Why did decision X lead to outcome Y?
│   └─► TIER 3: Get-CausalPath -FromLabel "..." -ToLabel "..."
│
├─► What patterns have high success rate?
│   └─► TIER 3: Get-Patterns -MinSuccessRate 0.7
│
├─► Need to store new knowledge?
│   │
│   ├─ From completed session?
│   │   └─► Extract-SessionEpisode.ps1 → Update-CausalGraph.ps1
│   │
│   └─ Factual knowledge?
│       └─► Use using-forgetful-memory skill or Serena write_memory
│
└─► Not sure which tier?
    └─► Start with TIER 1 (Search-Memory), escalate if insufficient
```

---

## Architecture

```text
┌────────────────────────────────────────────────────────────────┐
│                    TIER 0: Working Memory                       │
│              Current context window (Claude manages)            │
│                    [Always available]                           │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│                    TIER 1: Semantic Memory                      │
│           Serena (lexical) + Forgetful (vector)                 │
│                                                                 │
│  Scripts: Search-Memory.ps1, MemoryRouter.psm1                  │
│  Storage: .serena/memories/*.md + Forgetful MCP                 │
│  ADR: ADR-037 (Memory Router)                                   │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│                    TIER 2: Episodic Memory                      │
│         Session transcripts → structured episodes               │
│                                                                 │
│  Scripts: Extract-SessionEpisode.ps1, ReflexionMemory.psm1     │
│  Storage: .agents/memory/episodes/*.json                        │
│  ADR: ADR-038 (Reflexion Memory Schema)                        │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│                    TIER 3: Causal Memory                        │
│        Decision → outcome graphs, pattern discovery             │
│                                                                 │
│  Scripts: Update-CausalGraph.ps1, ReflexionMemory.psm1         │
│  Storage: .agents/memory/causality/causal-graph.json           │
│  ADR: ADR-038 (Reflexion Memory Schema)                        │
└────────────────────────────────────────────────────────────────┘
```

### Learning Cycle

```text
Sessions → Episodes → Causal Graph → Patterns → Better Decisions → Sessions
    ▲                                                                  │
    └──────────────────────────────────────────────────────────────────┘
```

---

## Scripts Reference

### Test-MemoryHealth.ps1

Health check for all tiers. **Run first when diagnosing issues.**

```powershell
# JSON output (for programmatic use)
pwsh .claude/skills/memory/scripts/Test-MemoryHealth.ps1

# Table output (for human viewing)
pwsh .claude/skills/memory/scripts/Test-MemoryHealth.ps1 -Format Table
```

**Output includes:**
- Overall status: healthy / degraded / unhealthy
- Per-tier availability
- Module load status
- Recommendations for fixes

---

### Search-Memory.ps1 (Tier 1)

Unified search across Serena and Forgetful.

```powershell
# Unified search (recommended)
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "PowerShell arrays"

# Serena only (fast, always available)
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks" -LexicalOnly

# Forgetful only (requires MCP running)
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "patterns" -SemanticOnly

# Limit results
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "error" -MaxResults 5
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-Query` | Yes | - | Search query (1-500 chars) |
| `-MaxResults` | No | 10 | Maximum results (1-100) |
| `-LexicalOnly` | No | false | Serena only (faster, no network) |
| `-SemanticOnly` | No | false | Forgetful only (requires MCP) |
| `-Format` | No | Json | Output format: Json or Table |

**Routing Strategy** (ADR-037): Serena-first with Forgetful augmentation. If Forgetful unavailable, automatically falls back to Serena only.

---

### Extract-SessionEpisode.ps1 (Tier 2)

Extract structured episode from session log.

```powershell
# Extract from session
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 `
  -SessionLogPath ".agents/sessions/2026-01-01-session-126.md"

# Overwrite existing
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 `
  -SessionLogPath ".agents/sessions/2026-01-01-session-126.md" `
  -Force
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-SessionLogPath` | Yes | - | Path to session log file |
| `-OutputPath` | No | .agents/memory/episodes/ | Output directory |
| `-Force` | No | false | Overwrite existing episode |

**Episode Schema** (ADR-038):

```json
{
  "id": "episode-2026-01-01-session-126",
  "session": "2026-01-01-session-126",
  "timestamp": "2026-01-01T10:00:00Z",
  "outcome": "success|partial|failure",
  "task": "Primary objective",
  "decisions": [...],
  "events": [...],
  "metrics": {...},
  "lessons": [...]
}
```

---

### Update-CausalGraph.ps1 (Tier 3)

Build causal relationships from episode data.

```powershell
# Update from all episodes
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1

# Update from specific episode
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1 `
  -EpisodePath ".agents/memory/episodes/episode-2026-01-01-session-126.json"

# Update from recent episodes
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1 -Since (Get-Date).AddDays(-7)

# Preview changes
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1 -DryRun
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-EpisodePath` | No | .agents/memory/episodes/ | Episode file or directory |
| `-Since` | No | - | Only process episodes since date |
| `-DryRun` | No | false | Preview without changes |

---

### ReflexionMemory.psm1 Functions

Import for programmatic access to Tier 2 and Tier 3:

```powershell
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1
```

**Episode Queries (Tier 2):**

```powershell
# Get specific episode
$episode = Get-Episode -SessionId "2026-01-01-session-126"

# Get recent failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)

# Get episodes for a task
$episodes = Get-Episodes -Task "memory system" -MaxResults 20
```

**Causal Queries (Tier 3):**

```powershell
# Trace causal path
$path = Get-CausalPath -FromLabel "error: test failure" -ToLabel "milestone: tests passing"

# Get high-success patterns
$patterns = Get-Patterns -MinSuccessRate 0.7

# Add nodes/edges (usually via Update-CausalGraph.ps1)
$node = Add-CausalNode -Type "decision" -Label "Used retry logic" -EpisodeId "episode-123"
$edge = Add-CausalEdge -SourceId $node.id -TargetId "outcome-456" -Type "causes" -Weight 0.8
```

---

### Measure-MemoryPerformance.ps1

Benchmark memory operations.

```powershell
# Default benchmarks
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1

# Custom queries
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1 `
  -Queries @("PowerShell", "git hooks") -Iterations 10

# Markdown report
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1 -Format markdown
```

**Performance Targets:**

| Metric | Target |
|--------|--------|
| Serena search | <600ms |
| Router overhead | <50ms |
| Total latency | <700ms |

---

## Common Workflows

### Workflow 1: Memory-First Decision Making

**Use when**: Starting any multi-step task

```text
1. Search-Memory.ps1 -Query "relevant topic"
2. Review results (check count > 0)
3. If memories found → apply patterns
4. If no memories → proceed with fresh approach
5. Reference memories in your response
```

### Workflow 2: Post-Session Learning

**Use when**: Session completed successfully

```text
1. Extract-SessionEpisode.ps1 -SessionLogPath "session.md"
   └─ Creates .agents/memory/episodes/episode-*.json

2. Update-CausalGraph.ps1
   └─ Adds nodes, edges, patterns to causal graph

3. Get-Patterns -MinSuccessRate 0.7
   └─ Review newly discovered patterns
```

### Workflow 3: Root Cause Analysis

**Use when**: Investigating repeated failures

```text
1. Get-Episodes -Outcome "failure" -Since 30days
   └─ Identify failure episodes

2. Get-CausalPath -FromLabel "error" -ToLabel "failure"
   └─ Trace what caused failures

3. Get-Patterns (filter for low success)
   └─ Identify anti-patterns

4. Search-Memory -Query "fix [error type]"
   └─ Find known solutions
```

### Workflow 4: Knowledge Discovery

**Use when**: Asked "what do you know about X"

```text
1. Test-MemoryHealth.ps1
   └─ Ensure all tiers available

2. Search-Memory -Query "X" -MaxResults 20
   └─ Tier 1 semantic search

3. Get-Episodes -Task "X"
   └─ Tier 2 session history

4. Get-Patterns (filter for "X")
   └─ Tier 3 causal patterns

5. Synthesize findings across tiers
```

---

## Anti-Patterns

| Anti-Pattern | Why It's Bad | Do This Instead |
|--------------|--------------|-----------------|
| **Skipping memory search** | Ignores institutional knowledge, repeats mistakes | Always search before multi-step reasoning |
| **Tier confusion** | Wrong tier returns irrelevant results | Follow decision tree explicitly |
| **Forgetful dependency** | Fails when MCP unavailable | Use `-LexicalOnly` fallback |
| **Stale causal graph** | Patterns become outdated | Run `Update-CausalGraph.ps1` after extractions |
| **Silent search failures** | Agent proceeds as if no memory exists | Check result count, log if empty |
| **Incomplete extraction** | Corrupts causal graph with bad data | Only extract from COMPLETED sessions |
| **Ignoring health check** | Operates on broken infrastructure | Run `Test-MemoryHealth.ps1` first when debugging |

---

## Error Recovery

| Error | Cause | Recovery |
|-------|-------|----------|
| "MemoryRouter module not found" | Path issue | Verify scripts in `.claude/skills/memory/scripts/` |
| "Forgetful MCP unavailable" | Server not running | Use `-LexicalOnly` or start Forgetful |
| "No episode files found" | Empty directory | Run `Extract-SessionEpisode.ps1` first |
| "Failed to read session log" | File not found | Verify session log path exists |
| "Causal graph empty" | Not initialized | Run `Update-CausalGraph.ps1` |
| Health check "degraded" | Partial availability | Read recommendations, fix issues |
| Health check "unhealthy" | Critical tier unavailable | Fix Tier 1 (Serena) issues first |

---

## Verification

After using this skill, verify success:

| Operation | Verification |
|-----------|--------------|
| Search completed | Result count > 0 OR explicitly logged "no results" |
| Episode extracted | JSON file exists in `.agents/memory/episodes/` |
| Graph updated | Stats show nodes/edges/patterns added |
| Pattern query | Patterns array returned (may be empty) |
| Health check | All critical tiers show "available: true" |

**Quick verification command:**

```powershell
pwsh .claude/skills/memory/scripts/Test-MemoryHealth.ps1 -Format Table
```

---

## Storage Locations

| Data | Location | Format |
|------|----------|--------|
| Serena memories | `.serena/memories/*.md` | Markdown |
| Forgetful memories | HTTP MCP (vector DB) | JSON via API |
| Episodes | `.agents/memory/episodes/*.json` | JSON |
| Causal graph | `.agents/memory/causality/causal-graph.json` | JSON |
| Session logs | `.agents/sessions/*.md` | Markdown |

---

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `using-forgetful-memory` | Deep Forgetful-specific operations (create, update, link) |
| `curating-memories` | Memory maintenance (obsolete, deduplicate) |
| `exploring-knowledge-graph` | Multi-hop graph traversal |

**This skill** is the unified entry point. Use related skills for specialized operations.

---

## Extension Points

1. **New tier types**: Add spatial, relational, or temporal memory
2. **Alternative backends**: Swap Serena/Forgetful for new MCPs
3. **Custom extractors**: Parse different session log formats
4. **ML patterns**: Add ML-based pattern detection
5. **Visualization**: Generate graph visualizations from causal data

---

<details>
<summary><strong>Deep Dive: Memory Router (ADR-037)</strong></summary>

The Memory Router implements Serena-first routing with Forgetful augmentation:

```text
Query arrives
    │
    ├── Check Forgetful availability
    │   ├── Available → Query both, merge results
    │   └── Unavailable → Query Serena only
    │
    ├── Serena query (lexical, keyword matching)
    │   └── Always executes (Serena is local/reliable)
    │
    ├── Forgetful query (semantic, vector similarity)
    │   └── Adds semantic matches Serena missed
    │
    └── Merge and rank results
        └── Return unified result set
```

**Why Serena-first?**
- Travels with Git repository (portable)
- Always available (no network dependency)
- Fast (local file system)

**Why Forgetful augmentation?**
- Semantic similarity catches conceptual matches
- Cross-project knowledge (global scope)
- Automatic knowledge graph linking

</details>

<details>
<summary><strong>Deep Dive: Reflexion Memory (ADR-038)</strong></summary>

### Episode Schema

Episodes capture structured session data:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique episode identifier |
| `session` | string | Source session ID |
| `timestamp` | ISO8601 | When session occurred |
| `outcome` | enum | success, partial, failure |
| `task` | string | Primary objective |
| `decisions` | array | Decision objects with context, choice, outcome |
| `events` | array | Event objects (commits, errors, milestones) |
| `metrics` | object | Duration, commits, errors, files |
| `lessons` | array | Extracted lessons learned |

### Causal Graph Schema

The causal graph tracks relationships:

| Component | Description |
|-----------|-------------|
| **Nodes** | Decisions, events, outcomes from episodes |
| **Edges** | Causal relationships with weights |
| **Patterns** | Recurring sequences with success rates |

### Pattern Discovery

Patterns are extracted from episode sequences:

```text
Decision A → Event B → Outcome C (success)
Decision A → Event B → Outcome D (failure)

Pattern: "When A leads to B, C is 3x more likely than D"
```

</details>

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.2.0 | 2026-01-01 | Initial skill with 4-tier architecture, 7 scripts |
