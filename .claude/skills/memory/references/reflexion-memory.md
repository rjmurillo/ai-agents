# Reflexion Memory

## Overview

The Reflexion Memory module (`.claude/skills/memory/scripts/ReflexionMemory.psm1`) provides episodic replay and causal reasoning capabilities. This implements Tiers 2 and 3 of the memory architecture.

**ADR**: ADR-038 Reflexion Memory Schema

**Task**: M-005 (Phase 2A Memory System)

## Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                   Episodic Memory (Tier 2)                    │
│      Session transcripts, decision sequences, outcomes        │
│                    (.agents/memory/episodes/)                        │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│                    Causal Memory (Tier 3)                     │
│        Cause-effect graphs, counterfactual analysis           │
│                  (.agents/memory/causality/)                         │
└───────────────────────────────────────────────────────────────┘
```

## Core Concepts

### Episodic Memory

Episodes are structured extracts from session logs, optimized for replay and analysis.

**Key Features**:

- Decision sequences with timestamps
- Event chains (commits, errors, milestones)
- Outcome classification (success, partial, failure)
- Metrics (duration, tool calls, errors, recoveries)
- Lessons learned

**Token Efficiency**: Episodes are 500-2000 tokens vs 10K-50K tokens for full session logs.

### Causal Memory

Causal graphs track cause-effect relationships across episodes.

**Key Features**:

- Nodes: decisions, events, outcomes, patterns, errors
- Edges: causes, enables, prevents, correlates
- Patterns: recurring successful/failed sequences
- Success rates: statistical tracking of pattern effectiveness

**Causal Integrity**: All edges have evidence count showing supporting episodes.

## Storage Formats

### Episode Schema

**Location**: `.agents/memory/episodes/episode-{session-id}.json`

```json
{
  "id": "episode-2026-01-01-session-126",
  "session": "2026-01-01-session-126",
  "timestamp": "2026-01-01T17:00:00Z",
  "outcome": "success",
  "task": "Implement MemoryRouter module",
  "decisions": [
    {
      "id": "d001",
      "timestamp": "2026-01-01T17:05:00Z",
      "type": "design",
      "context": "Choosing routing strategy",
      "chosen": "Serena-first routing",
      "rationale": "Lower latency, no network dependency",
      "outcome": "success",
      "effects": ["d002", "d003"]
    }
  ],
  "events": [
    {
      "id": "e001",
      "timestamp": "2026-01-01T17:10:00Z",
      "type": "commit",
      "content": "Created MemoryRouter.psm1",
      "caused_by": ["d001"],
      "leads_to": ["e002"]
    }
  ],
  "metrics": {
    "duration_minutes": 45,
    "tool_calls": 87,
    "errors": 2,
    "recoveries": 2,
    "commits": 3,
    "files_changed": 8
  },
  "lessons": [
    "Pre-commit hooks check all markdown, not just staged files",
    "Use --no-verify with documented justification for unrelated failures"
  ]
}
```

### Causal Graph Schema

**Location**: `.agents/memory/causality/causal-graph.json`

```json
{
  "version": "1.0",
  "updated": "2026-01-01T18:00:00Z",
  "nodes": [
    {
      "id": "n001",
      "type": "decision",
      "label": "Choose Serena-first routing",
      "episodes": ["episode-2026-01-01-126"],
      "frequency": 1,
      "success_rate": 1.0
    }
  ],
  "edges": [
    {
      "source": "n001",
      "target": "n002",
      "type": "causes",
      "weight": 0.95,
      "evidence_count": 1
    }
  ],
  "patterns": [
    {
      "id": "p001",
      "name": "Pre-commit bypass pattern",
      "description": "When lint errors are in unrelated files, use --no-verify with justification",
      "trigger": "E_MARKDOWNLINT_FAIL on unstaged files",
      "action": "Document justification, use --no-verify",
      "success_rate": 1.0,
      "occurrences": 2,
      "last_used": "2026-01-01T18:00:00Z"
    }
  ]
}
```

## Usage

### Episode Queries

```powershell
# Import module
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

# Get specific episode
$episode = Get-Episode -SessionId "2026-01-01-session-126"

# Get recent failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)

# Get all successes
$successes = Get-Episodes -Outcome "success" -MaxResults 50

# Get decision sequence from episode
$decisions = Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"
```

### Causal Queries

```powershell
# Add decision node
$node = Add-CausalNode -Type "decision" -Label "Choose Serena-first routing" -EpisodeId "episode-126"

# Add causal edge
$edge = Add-CausalEdge -SourceId "n001" -TargetId "n002" -Type "causes" -Weight 0.9

# Find causal path
$path = Get-CausalPath -FromLabel "routing decision" -ToLabel "performance target met" -MaxDepth 5

# Check if path was found
if ($path.found) {
    Write-Host "Path depth: $($path.depth)"
    foreach ($node in $path.path) {
        Write-Host "  - $($node.label)"
    }
}
```

### Pattern Queries

```powershell
# Get high-success patterns
$patterns = Get-Patterns -MinSuccessRate 0.7 -MinOccurrences 3

foreach ($pattern in $patterns) {
    Write-Host "$($pattern.name): $($pattern.success_rate * 100)% success over $($pattern.occurrences) uses"
    Write-Host "  Trigger: $($pattern.trigger)"
    Write-Host "  Action: $($pattern.action)"
}

# Get anti-patterns (low success rate)
$antiPatterns = Get-AntiPatterns -MaxSuccessRate 0.3

foreach ($ap in $antiPatterns) {
    Write-Host "AVOID: $($ap.name) - $($ap.success_rate * 100)% success rate"
}
```

### System Status

```powershell
# Get reflexion memory status
$status = Get-ReflexionMemoryStatus

Write-Host "Episodes: $($status.Episodes.Count) in $($status.Episodes.Path)"
Write-Host "Causal Graph:"
Write-Host "  Nodes: $($status.CausalGraph.Nodes)"
Write-Host "  Edges: $($status.CausalGraph.Edges)"
Write-Host "  Patterns: $($status.CausalGraph.Patterns)"
Write-Host "  Updated: $($status.CausalGraph.Updated)"
```

## Functions

### Episode Functions

#### Get-Episode

Retrieves an episode by session ID.

**Syntax**:

```powershell
Get-Episode -SessionId <String>
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| SessionId | String | Yes | Session identifier (e.g., "2026-01-01-session-126") |

**Returns**: `PSCustomObject` with episode data, or `$null` if not found.

**Example**:

```powershell
$episode = Get-Episode -SessionId "2026-01-01-session-126"
if ($episode) {
    Write-Host "Task: $($episode.task)"
    Write-Host "Outcome: $($episode.outcome)"
    Write-Host "Decisions: $($episode.decisions.Count)"
}
```

#### Get-Episodes

Retrieves episodes matching criteria.

**Syntax**:

```powershell
Get-Episodes
    [-Outcome <String>]
    [-Since <DateTime>]
    [-MaxResults <Int32>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| Outcome | String | No | - | Filter by outcome: success, partial, failure |
| Since | DateTime | No | - | Filter episodes since this date |
| MaxResults | Int32 | No | 20 | Maximum number of episodes to return (1-100) |

**Returns**: Array of `PSCustomObject` sorted by timestamp descending.

**Example**:

```powershell
# Get last week's failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)

foreach ($ep in $failures) {
    Write-Host "$($ep.session): $($ep.task) - $($ep.lessons.Count) lessons learned"
}
```

#### New-Episode

Creates a new episode from structured data.

**Syntax**:

```powershell
New-Episode
    -SessionId <String>
    -Task <String>
    -Outcome <String>
    [-Decisions <Array>]
    [-Events <Array>]
    [-Lessons <Array>]
    [-Metrics <Hashtable>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| SessionId | String | Yes | - | Source session identifier |
| Task | String | Yes | - | High-level task description |
| Outcome | String | Yes | - | Episode outcome: success, partial, failure |
| Decisions | Array | No | @() | Array of decision objects |
| Events | Array | No | @() | Array of event objects |
| Lessons | Array | No | @() | Array of lesson strings |
| Metrics | Hashtable | No | @{} | Metrics hashtable |

**Returns**: Hashtable with episode data. Also writes JSON file to `.agents/memory/episodes/`.

**Example**:

```powershell
$episode = New-Episode `
    -SessionId "2026-01-01-session-130" `
    -Task "Implement feature X" `
    -Outcome "success" `
    -Decisions @(
        @{
            id = "d001"
            timestamp = (Get-Date).ToString("o")
            type = "design"
            context = "Choosing architecture"
            chosen = "Event-driven design"
            rationale = "Better scalability"
            outcome = "success"
            effects = @()
        }
    ) `
    -Lessons @("Event-driven design reduced coupling")
```

#### Get-DecisionSequence

Retrieves the decision sequence from an episode.

**Syntax**:

```powershell
Get-DecisionSequence -EpisodeId <String>
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| EpisodeId | String | Yes | Episode identifier (e.g., "episode-2026-01-01-126") |

**Returns**: Array of decision objects sorted by timestamp.

**Example**:

```powershell
$decisions = Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"

foreach ($d in $decisions) {
    Write-Host "$($d.timestamp): $($d.type) - $($d.chosen)"
}
```

### Causal Graph Functions

#### Add-CausalNode

Adds a node to the causal graph.

**Syntax**:

```powershell
Add-CausalNode
    -Type <String>
    -Label <String>
    [-EpisodeId <String>]
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| Type | String | Yes | Node type: decision, event, outcome, pattern, error |
| Label | String | Yes | Human-readable label |
| EpisodeId | String | No | Source episode ID |

**Returns**: Hashtable with node data. Returns existing node (with updated frequency) if label already exists.

**Example**:

```powershell
$node = Add-CausalNode `
    -Type "decision" `
    -Label "Choose Serena-first routing" `
    -EpisodeId "episode-2026-01-01-126"

Write-Host "Node ID: $($node.id), Frequency: $($node.frequency)"
```

#### Add-CausalEdge

Adds an edge to the causal graph.

**Syntax**:

```powershell
Add-CausalEdge
    -SourceId <String>
    -TargetId <String>
    -Type <String>
    [-Weight <Double>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| SourceId | String | Yes | - | Source node ID |
| TargetId | String | Yes | - | Target node ID |
| Type | String | Yes | - | Edge type: causes, enables, prevents, correlates |
| Weight | Double | No | 0.5 | Confidence weight (0-1) |

**Returns**: Hashtable with edge data. Returns existing edge (with updated weight via running average) if edge exists.

**Example**:

```powershell
$edge = Add-CausalEdge `
    -SourceId "n001" `
    -TargetId "n002" `
    -Type "causes" `
    -Weight 0.9

Write-Host "Edge weight: $($edge.weight), Evidence: $($edge.evidence_count)"
```

#### Get-CausalPath

Finds causal path between two nodes using breadth-first search.

**Syntax**:

```powershell
Get-CausalPath
    -FromLabel <String>
    -ToLabel <String>
    [-MaxDepth <Int32>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| FromLabel | String | Yes | - | Source node label (partial match supported) |
| ToLabel | String | Yes | - | Target node label (partial match supported) |
| MaxDepth | Int32 | No | 5 | Maximum path depth to search (1-10) |

**Returns**: Hashtable with:

- `found`: Boolean indicating if path was found
- `path`: Array of node objects along the path
- `depth`: Number of edges in the path (if found)
- `error`: Error message (if not found)

**Example**:

```powershell
$path = Get-CausalPath `
    -FromLabel "routing decision" `
    -ToLabel "performance target" `
    -MaxDepth 5

if ($path.found) {
    Write-Host "Found path with $($path.depth) edges:"
    foreach ($node in $path.path) {
        Write-Host "  -> $($node.label)"
    }
}
else {
    Write-Host "No path found: $($path.error)"
}
```

### Pattern Functions

#### Add-Pattern

Adds a pattern to the causal graph.

**Syntax**:

```powershell
Add-Pattern
    -Name <String>
    -Trigger <String>
    -Action <String>
    [-Description <String>]
    [-SuccessRate <Double>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| Name | String | Yes | - | Pattern name |
| Trigger | String | Yes | - | Condition that triggers this pattern |
| Action | String | Yes | - | Recommended action |
| Description | String | No | - | Pattern description |
| SuccessRate | Double | No | 1.0 | Success rate (0-1) |

**Returns**: Hashtable with pattern data. Returns existing pattern (with updated occurrences and success_rate) if name exists.

**Example**:

```powershell
$pattern = Add-Pattern `
    -Name "Lint bypass" `
    -Trigger "Unrelated lint errors in pre-commit hook" `
    -Action "Use --no-verify with justification in commit message" `
    -Description "Pattern for handling unrelated linting failures" `
    -SuccessRate 1.0

Write-Host "Pattern added: $($pattern.id), Occurrences: $($pattern.occurrences)"
```

#### Get-Patterns

Retrieves patterns matching criteria.

**Syntax**:

```powershell
Get-Patterns
    [-MinSuccessRate <Double>]
    [-MinOccurrences <Int32>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| MinSuccessRate | Double | No | 0 | Minimum success rate filter (0-1) |
| MinOccurrences | Int32 | No | 1 | Minimum occurrences filter (1-1000) |

**Returns**: Array of pattern objects sorted by success_rate descending.

**Example**:

```powershell
# Get proven patterns (70%+ success, 3+ uses)
$proven = Get-Patterns -MinSuccessRate 0.7 -MinOccurrences 3

foreach ($p in $proven) {
    Write-Host "$($p.name):"
    Write-Host "  Success: $($p.success_rate * 100)%"
    Write-Host "  Uses: $($p.occurrences)"
    Write-Host "  Last: $($p.last_used)"
}
```

#### Get-AntiPatterns

Retrieves anti-patterns (low success rate patterns).

**Syntax**:

```powershell
Get-AntiPatterns
    [-MaxSuccessRate <Double>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| MaxSuccessRate | Double | No | 0.3 | Maximum success rate to qualify as anti-pattern (0-1) |

**Returns**: Array of anti-pattern objects sorted by success_rate ascending. Only includes patterns with at least 2 occurrences.

**Example**:

```powershell
# Get patterns that usually fail
$antiPatterns = Get-AntiPatterns -MaxSuccessRate 0.3

foreach ($ap in $antiPatterns) {
    Write-Host "AVOID: $($ap.name)"
    Write-Host "  Failure rate: $((1 - $ap.success_rate) * 100)%"
    Write-Host "  Failed $($ap.occurrences) times"
}
```

### Status Functions

#### Get-ReflexionMemoryStatus

Gets the status of the reflexion memory system.

**Syntax**:

```powershell
Get-ReflexionMemoryStatus
```

**Returns**: `PSCustomObject` with:

- `Episodes`: Path and count of episode files
- `CausalGraph`: Path, version, updated timestamp, node/edge/pattern counts
- `Configuration`: EpisodesPath and CausalityPath settings

**Example**:

```powershell
$status = Get-ReflexionMemoryStatus

Write-Host "=== Reflexion Memory Status ==="
Write-Host "Episodes:"
Write-Host "  Path: $($status.Episodes.Path)"
Write-Host "  Count: $($status.Episodes.Count)"
Write-Host ""
Write-Host "Causal Graph:"
Write-Host "  Version: $($status.CausalGraph.Version)"
Write-Host "  Nodes: $($status.CausalGraph.Nodes)"
Write-Host "  Edges: $($status.CausalGraph.Edges)"
Write-Host "  Patterns: $($status.CausalGraph.Patterns)"
Write-Host "  Updated: $($status.CausalGraph.Updated)"
```

## Scripts

### Extract-SessionEpisode.ps1

Extracts episode data from session logs.

**Syntax**:

```powershell
pwsh scripts/Extract-SessionEpisode.ps1
    -SessionLogPath <String>
    [-OutputPath <String>]
    [-Force]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| SessionLogPath | String | Yes | - | Path to session log file |
| OutputPath | String | No | .agents/memory/episodes/ | Output directory for episode JSON |
| Force | Switch | No | - | Overwrite existing episode file |

**Extraction Targets**:

- Session metadata (date, objectives, status)
- Decisions made during the session
- Events (commits, errors, milestones, tests)
- Metrics (duration, file counts, errors, recoveries)
- Lessons learned

**Example**:

```bash
pwsh scripts/Extract-SessionEpisode.ps1 \
    -SessionLogPath ".agents/sessions/2026-01-01-session-126.md"

# Output:
# Episode extracted:
#   ID:        episode-2026-01-01-session-126
#   Session:   2026-01-01-session-126
#   Outcome:   success
#   Decisions: 5
#   Events:    12
#   Lessons:   3
#   Output:    .agents/memory/episodes/episode-2026-01-01-session-126.json
```

### Update-CausalGraph.ps1

Updates the causal graph from episode data.

**Syntax**:

```powershell
pwsh scripts/Update-CausalGraph.ps1
    [-EpisodePath <String>]
    [-Since <DateTime>]
    [-DryRun]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| EpisodePath | String | No | .agents/memory/episodes/ | Path to episode file or directory |
| Since | DateTime | No | - | Only process episodes since this date |
| DryRun | Switch | No | - | Show what would be updated without making changes |

**Processing**:

- Adds decision nodes and their relationships
- Adds event nodes and causal chains
- Builds error-recovery chains
- Extracts patterns from decision sequences
- Updates success rates based on outcomes

**Example**:

```bash
# Update from all episodes
pwsh scripts/Update-CausalGraph.ps1

# Update from last week only
pwsh scripts/Update-CausalGraph.ps1 -Since (Get-Date).AddDays(-7)

# Dry run to preview changes
pwsh scripts/Update-CausalGraph.ps1 -DryRun

# Output:
# ═══════════════════════════════════════════════════
# Causal Graph Update Complete
# ═══════════════════════════════════════════════════
#   Episodes processed: 3
#   Nodes added:        15
#   Edges added:        8
#   Patterns added:     2
```

## Integration

### With Retrospective Agent

The retrospective agent auto-extracts episodes at session end:

```powershell
# In retrospective agent workflow
$sessionLog = ".agents/sessions/$sessionId.md"

# Extract episode
& scripts/Extract-SessionEpisode.ps1 -SessionLogPath $sessionLog

# Update causal graph
& scripts/Update-CausalGraph.ps1 -EpisodePath ".agents/memory/episodes/episode-$sessionId.json"

# Store in Serena/Forgetful
$episodeSummary = "Episode $sessionId: $task outcome=$outcome"
# ... save to memory systems
```

### With Session Protocol

Episode extraction is part of session end checklist:

```markdown
## Session End (BLOCKING)

- [ ] Complete session log
- [ ] Extract episode: `scripts/Extract-SessionEpisode.ps1`
- [ ] Update causal graph: `scripts/Update-CausalGraph.ps1`
- [ ] Update Serena memory
- [ ] Commit all changes (including .agents/memory/episodes/ and .agents/memory/causality/)
```

### With Memory Router

Future enhancement to search episodes via Memory Router:

```powershell
# Not yet implemented - placeholder
Search-Memory -Query "routing decision" -IncludeEpisodes
```

## Use Cases

### Review Past Failures

```powershell
# Get last month's failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddMonths(-1)

foreach ($failure in $failures) {
    Write-Host "`n=== $($failure.session) ==="
    Write-Host "Task: $($failure.task)"
    Write-Host "`nLessons Learned:"
    foreach ($lesson in $failure.lessons) {
        Write-Host "  - $lesson"
    }

    # Find what caused the failure
    $errorEvents = $failure.events | Where-Object { $_.type -eq "error" }
    if ($errorEvents) {
        Write-Host "`nErrors:"
        foreach ($err in $errorEvents) {
            Write-Host "  - $($err.content)"
        }
    }
}
```

### Identify Success Patterns

```powershell
# Get patterns with 80%+ success rate and at least 3 occurrences
$successPatterns = Get-Patterns -MinSuccessRate 0.8 -MinOccurrences 3

Write-Host "=== Proven Success Patterns ==="
foreach ($pattern in $successPatterns) {
    Write-Host "`n$($pattern.name)"
    Write-Host "  Success Rate: $($pattern.success_rate * 100)%"
    Write-Host "  Occurrences: $($pattern.occurrences)"
    Write-Host "  When: $($pattern.trigger)"
    Write-Host "  Do: $($pattern.action)"
}
```

### Trace Root Cause

```powershell
# Find causal path from decision to failure
$path = Get-CausalPath -FromLabel "chose parallel implementation" -ToLabel "race condition error"

if ($path.found) {
    Write-Host "Root cause trace ($($path.depth) steps):"
    foreach ($node in $path.path) {
        Write-Host "  -> $($node.label) ($($node.type))"
    }
}
```

### Compare Decision Outcomes

```powershell
# Get all episodes with routing decisions
$routingEpisodes = Get-Episodes -MaxResults 100 | Where-Object {
    $_.decisions | Where-Object { $_.context -match "routing" }
}

# Group by outcome
$outcomes = $routingEpisodes | Group-Object -Property outcome

foreach ($group in $outcomes) {
    Write-Host "$($group.Name): $($group.Count) episodes"

    # Show common patterns
    $decisions = $group.Group.decisions | Where-Object { $_.context -match "routing" }
    $chosen = $decisions | Group-Object -Property chosen | Sort-Object Count -Descending

    foreach ($choice in $chosen) {
        Write-Host "  - $($choice.Name): $($choice.Count) times"
    }
}
```

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Get-Episode | <50ms | Single JSON file read |
| Get-Episodes | ~200ms | O(n) scan of episode directory |
| Get-DecisionSequence | <10ms | In-memory array sort |
| Add-CausalNode | ~50ms | Load, modify, save graph JSON |
| Add-CausalEdge | ~50ms | Load, modify, save graph JSON |
| Get-CausalPath | ~100ms | BFS traversal of graph |
| Get-Patterns | <20ms | Filter in-memory patterns array |
| Extract-SessionEpisode | ~500ms | Parse markdown, extract structured data |
| Update-CausalGraph | ~1s | Process episode, update graph |

**Scaling**: Causal graph may grow large over time. Pruning strategy needed for >1000 nodes.

## Best Practices

### For Agents

1. **Check patterns before deciding**: Use `Get-Patterns` to find proven approaches
2. **Avoid anti-patterns**: Use `Get-AntiPatterns` to identify failure-prone choices
3. **Learn from failures**: Query `Get-Episodes -Outcome "failure"` for similar scenarios
4. **Trace causality**: Use `Get-CausalPath` to understand why past approaches worked/failed

### For Episode Extraction

1. **Run at session end**: Extract episodes while session is fresh
2. **Update causal graph immediately**: Keep graph in sync with episodes
3. **Validate extraction**: Check episode JSON for completeness
4. **Commit with session**: Include episodes in session commit

### For Causal Graph Maintenance

1. **Regular updates**: Run `Update-CausalGraph.ps1` periodically
2. **Prune stale nodes**: Remove nodes with frequency=1 and old timestamps (future enhancement)
3. **Review patterns**: Manually verify high-occurrence patterns
4. **Monitor graph size**: Watch for performance degradation as graph grows

## Troubleshooting

### Episode Not Found

**Symptoms**: `Get-Episode` returns `$null`

**Solutions**:

1. Verify episode file exists: `Test-Path ".agents/memory/episodes/episode-$sessionId.json"`
2. Check session ID format: Must match file naming convention
3. Re-extract from session log: `scripts/Extract-SessionEpisode.ps1`

### Causal Graph Not Updating

**Symptoms**: `Update-CausalGraph.ps1` runs but graph unchanged

**Solutions**:

1. Check for JSON errors: Validate `.agents/memory/causality/causal-graph.json`
2. Verify episode format: Ensure decisions and events have required fields
3. Check write permissions: Ensure `.agents/memory/causality/` is writable
4. Review script output: Look for warnings about malformed episodes

### Path Not Found

**Symptoms**: `Get-CausalPath` returns `found: false`

**Solutions**:

1. Verify node labels exist: Check `causal-graph.json` for matching labels
2. Increase MaxDepth: Default 5 may be insufficient for long chains
3. Check label matching: Labels use partial match (`-like "*$label*"`)
4. Review graph connectivity: Ensure edges connect the relevant nodes

### Pattern Extraction Issues

**Symptoms**: `Update-CausalGraph.ps1` creates no patterns

**Solutions**:

1. Check decision outcomes: Patterns require outcome field
2. Verify decision structure: Ensure decisions have context, chosen, type fields
3. Review extraction logic: Check `Get-DecisionPattern` function
4. Add patterns manually: Use `Add-Pattern` if auto-extraction insufficient

## Related Documentation

- [Memory Router](memory-router.md) - Tier 1 semantic memory (Serena + Forgetful)
- [Benchmarking](benchmarking.md) - Performance measurement
- [API Reference](api-reference.md) - Complete function signatures
- ADR-038 - Reflexion Memory Schema
- ADR-007 - Memory-First Architecture
