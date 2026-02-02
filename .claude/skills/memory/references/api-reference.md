# Memory System API Reference

Complete reference for all public functions in the Phase 2A Memory System (v0.2.0).

## Module Index

| Module | Purpose | Location |
|--------|---------|----------|
| [MemoryRouter](#memoryrouter-module) | Unified memory search (Tier 1) | .claude/skills/memory/scripts/MemoryRouter.psm1 |
| [ReflexionMemory](#reflexionmemory-module) | Episodes and causality (Tiers 2 & 3) | .claude/skills/memory/scripts/ReflexionMemory.psm1 |

## MemoryRouter Module

### Search-Memory

Unified memory search across Serena and Forgetful.

**Syntax**:

```powershell
Search-Memory
    [-Query] <String>
    [-MaxResults <Int32>]
    [-SemanticOnly]
    [-LexicalOnly]
```

**Parameters**:

- **Query** (String, Required): Search query (1-500 chars, alphanumeric + safe punctuation)
  - Pattern: `^[a-zA-Z0-9\s\-.,_()&:]+$`
- **MaxResults** (Int32, Optional): Maximum results to return (1-100, default: 10)
- **SemanticOnly** (Switch, Optional): Force Forgetful-only search (fails if unavailable)
- **LexicalOnly** (Switch, Optional): Force Serena-only search (always available)

**Returns**: `PSCustomObject[]` with properties:

- `Name` (String): Memory name
- `Content` (String): Full memory content
- `Source` (String): "Serena" or "Forgetful"
- `Score` (Double): Relevance score (Serena: percentage, Forgetful: similarity)
- `Path` (String): File path (Serena only, nullable)
- `Hash` (String): SHA-256 content hash (64 chars, lowercase hex)

**Throws**:

- `Cannot specify both -SemanticOnly and -LexicalOnly`: Mutually exclusive switches
- `Forgetful is not available and -SemanticOnly was specified`: Forgetful required but not running
- `Cannot validate argument on parameter 'Query'`: Query validation failed (invalid characters or length)

**Example**:

```powershell
$results = Search-Memory -Query "PowerShell arrays" -MaxResults 5
foreach ($r in $results) {
    Write-Host "$($r.Name) (Source: $($r.Source), Score: $($r.Score))"
}
```

---

### Test-ForgetfulAvailable

Checks if Forgetful MCP is available with 30s caching.

**Syntax**:

```powershell
Test-ForgetfulAvailable
    [-Port <Int32>]
    [-Force]
```

**Parameters**:

- **Port** (Int32, Optional): Forgetful server port (default: 8020)
- **Force** (Switch, Optional): Skip cache and force fresh check

**Returns**: `Boolean` indicating availability

**Side Effects**: Updates health check cache with 30s TTL

**Example**:

```powershell
if (Test-ForgetfulAvailable) {
    Write-Host "Forgetful is available"
}
```

---

### Get-MemoryRouterStatus

Returns diagnostic information about the Memory Router.

**Syntax**:

```powershell
Get-MemoryRouterStatus
```

**Parameters**: None

**Returns**: `PSCustomObject` with properties:

- `Serena` (Hashtable):
  - `Available` (Boolean): Whether Serena path exists
  - `Path` (String): Configured Serena memory path
- `Forgetful` (Hashtable):
  - `Available` (Boolean): Whether Forgetful is reachable
  - `Endpoint` (String): Configured Forgetful MCP endpoint
- `Cache` (Hashtable):
  - `AgeSeconds` (Double): Seconds since last health check (-1 if never checked)
  - `TTLSeconds` (Double): Cache time-to-live (30s)
- `Configuration` (Hashtable):
  - `SerenaPath` (String): Serena memory directory
  - `ForgetfulPort` (Int32): Forgetful server port
  - `ForgetfulTimeout` (Int32): TCP timeout in milliseconds
  - `MaxResults` (Int32): Default max results

**Example**:

```powershell
$status = Get-MemoryRouterStatus
Write-Host "Serena: $($status.Serena.Available), Forgetful: $($status.Forgetful.Available)"
```

---

## ReflexionMemory Module

### Episode Functions

#### Get-Episode

Retrieves an episode by session ID.

**Syntax**:

```powershell
Get-Episode -SessionId <String>
```

**Parameters**:

- **SessionId** (String, Required): Session identifier (e.g., "2026-01-01-session-126")

**Returns**: `PSCustomObject` with episode data, or `$null` if not found

**Properties**:

- `id` (String): Episode identifier
- `session` (String): Source session ID
- `timestamp` (String): ISO 8601 timestamp
- `outcome` (String): "success", "partial", or "failure"
- `task` (String): High-level task description
- `decisions` (Array): Decision objects
- `events` (Array): Event objects
- `metrics` (Hashtable): Performance metrics
- `lessons` (Array): Lessons learned

**Example**:

```powershell
$episode = Get-Episode -SessionId "2026-01-01-session-126"
if ($episode) {
    Write-Host "Outcome: $($episode.outcome)"
}
```

---

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

- **Outcome** (String, Optional): Filter by outcome ("success", "partial", "failure")
- **Since** (DateTime, Optional): Filter episodes since this date
- **MaxResults** (Int32, Optional): Maximum results (1-100, default: 20)

**Returns**: `PSCustomObject[]` sorted by timestamp descending

**Example**:

```powershell
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)
```

---

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

- **SessionId** (String, Required): Source session identifier
- **Task** (String, Required): High-level task description
- **Outcome** (String, Required): "success", "partial", or "failure"
- **Decisions** (Array, Optional): Decision objects (default: @())
- **Events** (Array, Optional): Event objects (default: @())
- **Lessons** (Array, Optional): Lesson strings (default: @())
- **Metrics** (Hashtable, Optional): Metrics hashtable (default: @{})

**Returns**: Hashtable with episode data

**Side Effects**: Writes JSON file to `.agents/memory/episodes/episode-{SessionId}.json`

**Example**:

```powershell
$episode = New-Episode `
    -SessionId "2026-01-01-session-130" `
    -Task "Implement feature X" `
    -Outcome "success" `
    -Lessons @("Lesson 1", "Lesson 2")
```

---

#### Get-DecisionSequence

Retrieves the decision sequence from an episode.

**Syntax**:

```powershell
Get-DecisionSequence -EpisodeId <String>
```

**Parameters**:

- **EpisodeId** (String, Required): Episode identifier (e.g., "episode-2026-01-01-126")

**Returns**: `PSCustomObject[]` sorted by timestamp, or empty array if episode not found

**Example**:

```powershell
$decisions = Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"
foreach ($d in $decisions) {
    Write-Host "$($d.timestamp): $($d.chosen)"
}
```

---

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

- **Type** (String, Required): Node type ("decision", "event", "outcome", "pattern", "error")
- **Label** (String, Required): Human-readable label
- **EpisodeId** (String, Optional): Source episode ID

**Returns**: Hashtable with node data

**Properties**:

- `id` (String): Node ID (e.g., "n001")
- `type` (String): Node type
- `label` (String): Human-readable label
- `episodes` (Array): Episode IDs referencing this node
- `frequency` (Int32): Number of occurrences
- `success_rate` (Double): Success rate (0-1)

**Side Effects**: Updates `.agents/memory/causality/causal-graph.json`

**Deduplication**: If label exists, increments frequency and adds episode to list

**Example**:

```powershell
$node = Add-CausalNode -Type "decision" -Label "Choose routing" -EpisodeId "episode-126"
Write-Host "Node ID: $($node.id)"
```

---

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

- **SourceId** (String, Required): Source node ID
- **TargetId** (String, Required): Target node ID
- **Type** (String, Required): Edge type ("causes", "enables", "prevents", "correlates")
- **Weight** (Double, Optional): Confidence weight (0-1, default: 0.5)

**Returns**: Hashtable with edge data

**Properties**:

- `source` (String): Source node ID
- `target` (String): Target node ID
- `type` (String): Edge type
- `weight` (Double): Confidence weight (running average)
- `evidence_count` (Int32): Number of supporting episodes

**Side Effects**: Updates `.agents/memory/causality/causal-graph.json`

**Deduplication**: If edge exists, updates weight with running average and increments evidence count

**Example**:

```powershell
$edge = Add-CausalEdge -SourceId "n001" -TargetId "n002" -Type "causes" -Weight 0.9
Write-Host "Evidence count: $($edge.evidence_count)"
```

---

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

- **FromLabel** (String, Required): Source node label (partial match with `-like "*$label*"`)
- **ToLabel** (String, Required): Target node label (partial match with `-like "*$label*"`)
- **MaxDepth** (Int32, Optional): Maximum path depth (1-10, default: 5)

**Returns**: Hashtable with:

- `found` (Boolean): Whether path was found
- `path` (Array): Node objects along the path (empty if not found)
- `depth` (Int32): Number of edges in path (only if found)
- `error` (String): Error message (only if not found)

**Algorithm**: Breadth-first search with cycle detection

**Example**:

```powershell
$path = Get-CausalPath -FromLabel "decision" -ToLabel "outcome" -MaxDepth 5
if ($path.found) {
    Write-Host "Path depth: $($path.depth)"
    foreach ($node in $path.path) {
        Write-Host "  -> $($node.label)"
    }
}
```

---

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

- **Name** (String, Required): Pattern name
- **Trigger** (String, Required): Condition that triggers this pattern
- **Action** (String, Required): Recommended action
- **Description** (String, Optional): Pattern description
- **SuccessRate** (Double, Optional): Success rate (0-1, default: 1.0)

**Returns**: Hashtable with pattern data

**Properties**:

- `id` (String): Pattern ID (e.g., "p001")
- `name` (String): Pattern name
- `description` (String): Description
- `trigger` (String): Triggering condition
- `action` (String): Recommended action
- `success_rate` (Double): Success rate (running average)
- `occurrences` (Int32): Number of times pattern used
- `last_used` (String): ISO 8601 timestamp of last use

**Side Effects**: Updates `.agents/memory/causality/causal-graph.json`

**Deduplication**: If name exists, increments occurrences, updates success_rate, and sets last_used

**Example**:

```powershell
$pattern = Add-Pattern `
    -Name "Lint bypass" `
    -Trigger "Unrelated lint errors" `
    -Action "Use --no-verify with justification" `
    -SuccessRate 1.0
```

---

#### Get-Patterns

Retrieves patterns matching criteria.

**Syntax**:

```powershell
Get-Patterns
    [-MinSuccessRate <Double>]
    [-MinOccurrences <Int32>]
```

**Parameters**:

- **MinSuccessRate** (Double, Optional): Minimum success rate (0-1, default: 0)
- **MinOccurrences** (Int32, Optional): Minimum occurrences (1-1000, default: 1)

**Returns**: `PSCustomObject[]` sorted by success_rate descending

**Example**:

```powershell
$proven = Get-Patterns -MinSuccessRate 0.7 -MinOccurrences 3
foreach ($p in $proven) {
    Write-Host "$($p.name): $($p.success_rate * 100)% over $($p.occurrences) uses"
}
```

---

#### Get-AntiPatterns

Retrieves anti-patterns (low success rate patterns).

**Syntax**:

```powershell
Get-AntiPatterns
    [-MaxSuccessRate <Double>]
```

**Parameters**:

- **MaxSuccessRate** (Double, Optional): Maximum success rate (0-1, default: 0.3)

**Returns**: `PSCustomObject[]` sorted by success_rate ascending

**Filter**: Only includes patterns with at least 2 occurrences

**Example**:

```powershell
$antiPatterns = Get-AntiPatterns -MaxSuccessRate 0.3
foreach ($ap in $antiPatterns) {
    Write-Host "AVOID: $($ap.name) - $($ap.success_rate * 100)% success"
}
```

---

### Status Functions

#### Get-ReflexionMemoryStatus

Gets the status of the reflexion memory system.

**Syntax**:

```powershell
Get-ReflexionMemoryStatus
```

**Parameters**: None

**Returns**: `PSCustomObject` with properties:

- `Episodes` (Hashtable):
  - `Path` (String): Episodes directory path
  - `Count` (Int32): Number of episode files
- `CausalGraph` (Hashtable):
  - `Path` (String): Causal graph file path
  - `Version` (String): Schema version
  - `Updated` (String): Last update timestamp (ISO 8601)
  - `Nodes` (Int32): Number of nodes
  - `Edges` (Int32): Number of edges
  - `Patterns` (Int32): Number of patterns
- `Configuration` (Hashtable):
  - `EpisodesPath` (String): Episodes directory
  - `CausalityPath` (String): Causality directory

**Example**:

```powershell
$status = Get-ReflexionMemoryStatus
Write-Host "Episodes: $($status.Episodes.Count)"
Write-Host "Nodes: $($status.CausalGraph.Nodes)"
```

---

## Scripts

### Extract-SessionEpisode.ps1

Extracts episode data from session logs.

**Syntax**:

```powershell
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1
    -SessionLogPath <String>
    [-OutputPath <String>]
    [-Force]
```

**Parameters**:

- **SessionLogPath** (String, Required): Path to session log file (must exist)
- **OutputPath** (String, Optional): Output directory (default: `.agents/memory/episodes/`)
- **Force** (Switch, Optional): Overwrite existing episode file

**Returns**: Hashtable with episode data (also printed to console)

**Exit Codes**:

- `0`: Success
- `1`: Failed to read session log, write episode file, or episode already exists without `-Force`

**Example**:

```bash
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 \
    -SessionLogPath ".agents/sessions/2026-01-01-session-126.json"
```

---

### Update-CausalGraph.ps1

Updates the causal graph from episode data.

**Syntax**:

```powershell
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1
    [-EpisodePath <String>]
    [-Since <DateTime>]
    [-DryRun]
```

**Parameters**:

- **EpisodePath** (String, Optional): Path to episode file or directory (default: `.agents/memory/episodes/`)
- **Since** (DateTime, Optional): Only process episodes since this date
- **DryRun** (Switch, Optional): Show what would be updated without making changes

**Returns**: `PSCustomObject` with statistics:

- `episodes_processed` (Int32): Number of episodes processed
- `nodes_added` (Int32): Number of nodes added
- `edges_added` (Int32): Number of edges added
- `patterns_added` (Int32): Number of patterns added

**Exit Codes**:

- `0`: Success or no episodes to process
- `1`: Module not found or critical error

**Example**:

```bash
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1 -Since (Get-Date).AddDays(-7)
```

---

## Data Types

### Decision Object

```powershell
@{
    id        = "d001"                    # String: Decision ID
    timestamp = "2026-01-01T17:05:00Z"   # String: ISO 8601 timestamp
    type      = "design"                  # String: design|implementation|test|recovery|routing
    context   = "Choosing routing"       # String: Decision context
    chosen    = "Serena-first"           # String: Chosen option
    rationale = "Lower latency"          # String: Rationale
    outcome   = "success"                 # String: success|partial|failure
    effects   = @("d002", "d003")        # Array: IDs of affected decisions/events
}
```

### Event Object

```powershell
@{
    id        = "e001"                    # String: Event ID
    timestamp = "2026-01-01T17:10:00Z"   # String: ISO 8601 timestamp
    type      = "commit"                  # String: tool_call|commit|error|milestone|test|handoff
    content   = "Created module"         # String: Event description
    caused_by = @("d001")                # Array: IDs of causing decisions
    leads_to  = @("e002")                # Array: IDs of resulting events
}
```

### Metrics Object

```powershell
@{
    duration_minutes = 45      # Int32: Session duration
    tool_calls       = 87      # Int32: Number of tool invocations
    errors           = 2       # Int32: Error count
    recoveries       = 2       # Int32: Recovery count
    commits          = 3       # Int32: Commit count
    files_changed    = 8       # Int32: Files modified
}
```

---

## Error Handling

All functions follow PowerShell error handling conventions:

- **Terminating Errors**: Thrown via `throw` for invalid input or critical failures
- **Non-Terminating Errors**: Written via `Write-Warning` for recoverable issues
- **Return Values**: `$null` or empty arrays for not-found scenarios (not exceptions)

**Error Action Preference**: All modules use `$ErrorActionPreference = 'Stop'` for strict error handling.

**Validation**: Input validation via `ValidatePattern`, `ValidateLength`, `ValidateRange`, `ValidateSet`

---

## Performance Characteristics

| Function | Typical Latency | Complexity |
|----------|----------------|------------|
| Search-Memory (Serena-only) | 530ms | O(n) file scan |
| Search-Memory (augmented) | 700ms | O(n) + network |
| Test-ForgetfulAvailable (cached) | <1ms | O(1) hash lookup |
| Test-ForgetfulAvailable (fresh) | 1-500ms | TCP connect |
| Get-MemoryRouterStatus | <10ms | File stats + cache read |
| Get-Episode | <50ms | JSON file read |
| Get-Episodes | ~200ms | O(n) directory scan |
| New-Episode | ~100ms | JSON serialization + write |
| Add-CausalNode | ~50ms | Load + modify + save |
| Add-CausalEdge | ~50ms | Load + modify + save |
| Get-CausalPath | ~100ms | BFS traversal |
| Get-Patterns | <20ms | In-memory filter |
| Get-ReflexionMemoryStatus | <50ms | File stats + JSON read |

**Note**: Latencies assume SSD storage and hot filesystem cache.

---

## Related Documentation

- [Memory Router](memory-router.md) - Detailed Memory Router usage
- [Reflexion Memory](reflexion-memory.md) - Detailed Reflexion Memory usage
- [Benchmarking](benchmarking.md) - Performance measurement
- [Quick Start Guide](quick-start.md) - Common usage patterns
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
