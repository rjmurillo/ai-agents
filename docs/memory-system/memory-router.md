# Memory Router

## Overview

The Memory Router (`scripts/MemoryRouter.psm1`) provides unified memory search across Serena (lexical) and Forgetful (semantic) memory systems with Serena-first routing.

**ADR**: ADR-037 Memory Router Architecture

**Task**: M-003 (Phase 2A Memory System)

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     Memory Router                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Search-Memory -Query "pattern" -MaxResults 10       │    │
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

## Core Concepts

### Serena-First Routing

The Memory Router always queries Serena first (canonical source), then optionally augments with Forgetful semantic results.

**Rationale**: Serena travels with the Git repository, ensuring cross-platform availability. Forgetful provides enhanced semantic search but requires a running service.

### Result Augmentation

Forgetful results enhance but never replace Serena results.

**Merge Strategy**:

1. Query Serena (always)
2. Query Forgetful (if available and not LexicalOnly)
3. Deduplicate by SHA-256 content hash
4. Return Serena results + unique Forgetful matches

### Availability Detection

The router automatically detects Forgetful availability using a cached TCP health check (30s TTL, 500ms timeout).

**Failure Mode**: Gracefully degrades to Serena-only if Forgetful unavailable.

## Usage

### Basic Search

```powershell
# Import module
Import-Module scripts/MemoryRouter.psm1

# Unified search (Serena + Forgetful if available)
$results = Search-Memory -Query "PowerShell array handling" -MaxResults 10

# Process results
foreach ($result in $results) {
    Write-Host "$($result.Name) (Source: $($result.Source), Score: $($result.Score))"
    Write-Host $result.Content
}
```

### Lexical-Only Search

Force Serena-only search (skip Forgetful):

```powershell
# Faster, no network calls
$results = Search-Memory -Query "git hooks" -LexicalOnly
```

**Use When**: Performance critical, or Forgetful known to be unavailable.

### Semantic-Only Search

Force Forgetful-only search (requires availability):

```powershell
# Requires Forgetful MCP running
try {
    $results = Search-Memory -Query "authentication patterns" -SemanticOnly
}
catch {
    Write-Warning "Forgetful unavailable: $($_.Exception.Message)"
}
```

**Use When**: Need semantic similarity specifically, not keyword matching.

### Via Skill (Agent-Facing)

Agents should use the skill script:

```bash
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks" -Format Json
```

**Output**: JSON with results and diagnostic info.

## Functions

### Search-Memory

Main entry point for unified memory search.

**Syntax**:

```powershell
Search-Memory
    [-Query] <String>
    [-MaxResults <Int32>]
    [-SemanticOnly]
    [-LexicalOnly]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| Query | String | Yes | - | Search query (1-500 chars, alphanumeric + safe punctuation) |
| MaxResults | Int32 | No | 10 | Maximum results to return (1-100) |
| SemanticOnly | Switch | No | - | Force Forgetful-only search (fails if unavailable) |
| LexicalOnly | Switch | No | - | Force Serena-only search (always available) |

**Returns**: Array of `PSCustomObject` with:

- `Name`: Memory name
- `Content`: Full memory content
- `Source`: "Serena" or "Forgetful"
- `Score`: Relevance score (percentage for Serena, similarity for Forgetful)
- `Path`: File path (Serena only)
- `Hash`: SHA-256 content hash (for deduplication)

**Example**:

```powershell
$results = Search-Memory -Query "PowerShell arrays" -MaxResults 5

# Results structure:
# [
#   {
#     Name: "powershell-array-handling",
#     Content: "PowerShell arrays need @() for...",
#     Source: "Serena",
#     Score: 66.67,
#     Path: ".serena/memories/powershell-array-handling.md",
#     Hash: "a3b5c7..."
#   },
#   ...
# ]
```

### Test-ForgetfulAvailable

Checks if Forgetful MCP is available with 30s caching.

**Syntax**:

```powershell
Test-ForgetfulAvailable
    [-Port <Int32>]
    [-Force]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| Port | Int32 | No | 8020 | Forgetful server port |
| Force | Switch | No | - | Skip cache and force fresh check |

**Returns**: `Boolean` indicating availability.

**Example**:

```powershell
if (Test-ForgetfulAvailable) {
    Write-Host "Forgetful is available"
}
else {
    Write-Host "Forgetful is unavailable, using Serena-only"
}
```

### Get-MemoryRouterStatus

Returns diagnostic information about the Memory Router.

**Syntax**:

```powershell
Get-MemoryRouterStatus
```

**Returns**: `PSCustomObject` with:

- `Serena`: Availability and path
- `Forgetful`: Availability and endpoint
- `Cache`: Health check cache age and TTL
- `Configuration`: Current settings

**Example**:

```powershell
$status = Get-MemoryRouterStatus

# Output:
# Serena:
#   Available: True
#   Path: .serena/memories
# Forgetful:
#   Available: True
#   Endpoint: http://localhost:8020/mcp
# Cache:
#   AgeSeconds: 12.5
#   TTLSeconds: 30
# Configuration:
#   SerenaPath: .serena/memories
#   ForgetfulPort: 8020
#   ForgetfulTimeout: 500
#   MaxResults: 10
```

## Internal Functions (Private)

### Invoke-SerenaSearch

Performs lexical search across Serena memory files.

**Scoring**: Percentage of query keywords matching in filename.

**Steps**:

1. Extract keywords from query (length > 2 chars)
2. List all `.md` files in `.serena/memories/`
3. Match keywords against file basenames
4. Calculate score as `(matching_keywords / total_keywords) * 100`
5. Read content for matched files
6. Sort by score descending

### Invoke-ForgetfulSearch

Performs semantic search via Forgetful MCP HTTP endpoint.

**Protocol**: JSON-RPC 2.0 over HTTP

**Steps**:

1. Build JSON-RPC request with `memory_search` tool
2. POST to `http://localhost:8020/mcp`
3. Parse MCP tool response
4. Extract memories from response content
5. Return structured results

### Merge-MemoryResults

Merges and deduplicates results from Serena and Forgetful.

**Algorithm**:

1. Create hash set from Serena results (SHA-256 of content)
2. Add all Serena results to merged set
3. For each Forgetful result:
   - Hash content
   - If hash not in set, add to merged results
   - Mark hash as seen
4. Limit to MaxResults

**Serena Priority**: Serena results appear first and are the canonical version on content collision.

### Get-ContentHash

Computes SHA-256 hash of content for deduplication.

**Algorithm**: SHA-256 over UTF-8 bytes, lowercase hex output.

## Configuration

Configuration is stored in module-level script variables:

```powershell
$script:Config = @{
    SerenaPath       = ".serena/memories"
    ForgetfulPort    = 8020
    ForgetfulTimeout = 500  # milliseconds
    MaxResults       = 10
}
```

**Customization**: These can be modified after module import if needed (not recommended).

## Health Check Details

### Cache Strategy

**TTL**: 30 seconds

**Rationale**: Balances freshness vs latency overhead. Forgetful availability is stable within a session.

### TCP Check

**Method**: Attempt TCP connection to `localhost:8020`

**Timeout**: 500ms

**Rationale**: Fast enough for per-session check. Slower services fail early instead of blocking queries.

### Failure Handling

**On Failure**: Cache `Available = false` for 30s, return false immediately.

**No Retry**: Failed health checks are not retried until cache expires.

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Serena search | ~530ms | O(n) file scan + keyword match |
| Forgetful search | Variable | Network + embedding + vector search |
| Health check (cached) | <1ms | Hash table lookup |
| Health check (fresh) | 1-500ms | TCP connect with timeout |
| Result merge | <10ms | Hash-based deduplication |
| **Total (Serena-only)** | ~530ms | Baseline, no network |
| **Total (augmented)** | ~700ms | Serena + Forgetful + merge |

**Target**: Router overhead < 50ms when Forgetful available.

## Security

### Input Validation

All query inputs are validated:

```powershell
[ValidatePattern('^[a-zA-Z0-9\s\-.,_()&:]+$')]  # Alphanumeric + safe punctuation
[ValidateLength(1, 500)]                         # Reasonable length limits
[string]$Query
```

**Prevents**:

- Regex injection (CWE-20)
- Buffer overflow (CWE-120)
- Path traversal (CWE-22)
- Command injection (CWE-78)

### Transport Security

| Connection | Protocol | Security |
|------------|----------|----------|
| Serena | Local file I/O | No network exposure |
| Forgetful | HTTP localhost:8020 | Localhost-only (no TLS) |

**Assumption**: Forgetful runs on localhost only. Remote deployment would require HTTPS.

### Data Handling

- **No secrets in queries**: Queries should not contain credentials, API keys, or PII
- **Content hashing**: SHA-256 for deduplication (cryptographically secure)
- **Logging**: Query patterns logged for debugging; content NOT logged

## Error Handling

### Forgetful Unavailable

```powershell
$results = Search-Memory -Query "test"
# Returns Serena results only, no error
```

### Forgetful Required but Unavailable

```powershell
Search-Memory -Query "test" -SemanticOnly
# Throws: "Forgetful is not available and -SemanticOnly was specified"
```

### Invalid Query

```powershell
Search-Memory -Query "test; rm -rf /"
# Throws: "Cannot validate argument on parameter 'Query'"
```

### Mutually Exclusive Switches

```powershell
Search-Memory -Query "test" -SemanticOnly -LexicalOnly
# Throws: "Cannot specify both -SemanticOnly and -LexicalOnly"
```

## Troubleshooting

### Forgetful Not Detected

**Symptoms**: `Test-ForgetfulAvailable` returns false, but Forgetful is running.

**Diagnosis**:

```powershell
# Force fresh health check
Test-ForgetfulAvailable -Force

# Check endpoint manually
Invoke-RestMethod -Uri "http://localhost:8020/mcp" -Method Get
```

**Solutions**:

1. Verify Forgetful is running: `systemctl --user status forgetful` (Linux)
2. Check port: `netstat -an | grep 8020`
3. Review Forgetful logs: `journalctl --user -u forgetful -n 50`

### No Serena Results

**Symptoms**: `Search-Memory` returns empty results, but memories exist.

**Diagnosis**:

```powershell
# Check Serena path exists
Test-Path ".serena/memories"

# List memory files
Get-ChildItem ".serena/memories" -Filter "*.md"
```

**Solutions**:

1. Verify `.serena/memories/` directory exists
2. Check query keywords match file names
3. Try broader query with common terms

### Slow Searches

**Symptoms**: Searches take >1 second consistently.

**Diagnosis**:

```powershell
# Time Serena-only search
Measure-Command { Search-Memory -Query "test" -LexicalOnly }

# Time augmented search
Measure-Command { Search-Memory -Query "test" }
```

**Solutions**:

1. Use `-LexicalOnly` if semantic search not needed
2. Reduce `-MaxResults` to minimize file reads
3. Check Forgetful response time (may be slow on first query)

## Best Practices

### For Agents

1. **Always use Search-Memory**: Don't call Serena/Forgetful MCP directly
2. **Specify MaxResults**: Limit to what you actually need (default 10 is reasonable)
3. **Check availability**: Use `Test-ForgetfulAvailable` if semantic search is critical
4. **Handle empty results**: Always check `$results.Count` before processing

### For Skill Authors

1. **Use skill script**: Call `.claude/skills/memory/scripts/Search-Memory.ps1`
2. **Parse JSON output**: Skill returns structured JSON for programmatic use
3. **Include diagnostics**: Skill output includes `Get-MemoryRouterStatus`

### For Developers

1. **Test both modes**: Verify Serena-only and augmented searches
2. **Mock health checks**: Use `-LexicalOnly` in tests to avoid network dependency
3. **Validate input**: Never bypass `ValidatePattern` checks
4. **Profile performance**: Use `Measure-MemoryPerformance.ps1` for benchmarking

## Related Documentation

- [Reflexion Memory](reflexion-memory.md) - Episodic and causal memory (Tiers 2 & 3)
- [Benchmarking](benchmarking.md) - Performance measurement
- [API Reference](api-reference.md) - Complete function signatures
- ADR-037 - Memory Router Architecture
- ADR-007 - Memory-First Architecture
