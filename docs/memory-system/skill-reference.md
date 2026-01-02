# Memory System Skill Reference

## Overview

The memory system exposes functionality through Claude Code skills - standardized PowerShell scripts that agents can invoke. This document provides complete reference for all memory-related skills.

## Skill Location

```text
.claude/
└── skills/
    └── memory/
        └── scripts/
            └── Search-Memory.ps1
```

## Search-Memory.ps1

### Synopsis

Unified memory search across Serena and Forgetful.

### Description

Agent-facing skill script that wraps MemoryRouter.psm1. Provides unified memory search with Serena-first routing and optional Forgetful augmentation per ADR-037.

### Syntax

```powershell
Search-Memory.ps1
    -Query <String>
    [-MaxResults <Int32>]
    [-LexicalOnly]
    [-SemanticOnly]
    [-Format <String>]
```

### Parameters

#### -Query

Search query string.

| Property | Value |
|----------|-------|
| Type | String |
| Position | 0 |
| Required | Yes |
| Length | 1-500 characters |
| Pattern | `^[a-zA-Z0-9\s\-.,_()&:]+$` |

**Allowed Characters**:

- Letters (a-z, A-Z)
- Numbers (0-9)
- Spaces
- Punctuation: `-` `.` `,` `_` `(` `)` `&` `:`

**Examples**:

```text
"PowerShell arrays"           # Valid
"git hooks: pre-commit"       # Valid
"authentication (OAuth 2.0)"  # Valid
"invalid<script>query"        # Invalid - special characters
```

#### -MaxResults

Maximum number of results to return.

| Property | Value |
|----------|-------|
| Type | Int32 |
| Position | Named |
| Required | No |
| Default | 10 |
| Range | 1-100 |

#### -LexicalOnly

Search only Serena (lexical/file-based). Faster and requires no network access.

| Property | Value |
|----------|-------|
| Type | Switch |
| Position | Named |
| Required | No |

**Use When**:

- Forgetful is unavailable
- Performance is critical
- Exact keyword matching is needed
- Offline operation required

#### -SemanticOnly

Search only Forgetful (semantic/vector). Requires Forgetful MCP server running.

| Property | Value |
|----------|-------|
| Type | Switch |
| Position | Named |
| Required | No |

**Use When**:

- Need conceptual similarity matching
- Keywords are ambiguous
- Exploring related topics
- Finding context without exact terms

**Note**: Will fail if Forgetful is not available. Use try/catch with fallback to LexicalOnly.

#### -Format

Output format for results.

| Property | Value |
|----------|-------|
| Type | String |
| Position | Named |
| Required | No |
| Default | Json |
| Values | Json, Table |

**Json Format**: Structured output for programmatic consumption:

```json
{
  "Query": "PowerShell arrays",
  "Count": 3,
  "Source": "Unified",
  "Results": [...],
  "Diagnostic": {...}
}
```

**Table Format**: Human-readable formatted table:

```text
Name                    Source    Score Preview
----                    ------    ----- -------
powershell-arrays       Serena    1.0   PowerShell arrays need @() for...
array-handling          Forgetful 0.85  Common array gotchas include...
```

### Output Structure

#### JSON Output

```json
{
  "Query": "string",
  "Count": 0,
  "Source": "Unified|Serena|Forgetful",
  "Results": [
    {
      "Name": "memory-name",
      "Source": "Serena|Forgetful",
      "Score": 1.0,
      "Path": "/path/to/memory",
      "Content": "Full memory content..."
    }
  ],
  "Diagnostic": {
    "SerenaAvailable": true,
    "ForgetfulAvailable": true,
    "SerenaPath": "/path/to/.serena/memories",
    "SerenaMemoryCount": 460,
    "ForgetfulUrl": "http://localhost:8020"
  }
}
```

#### Error Output

```json
{
  "Error": "Error message",
  "Query": "original query",
  "Details": "Stack trace..."
}
```

### Examples

#### Example 1: Basic Search

```bash
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks"
```

Output:

```json
{
  "Query": "git hooks",
  "Count": 5,
  "Source": "Unified",
  "Results": [
    {
      "Name": "git-hooks-pre-commit",
      "Source": "Serena",
      "Score": 1.0,
      "Path": ".serena/memories/git-hooks-pre-commit.md",
      "Content": "Pre-commit hooks validate..."
    }
  ]
}
```

#### Example 2: Lexical Only with Table Format

```bash
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 \
    -Query "PowerShell arrays" \
    -LexicalOnly \
    -Format Table
```

Output:

```text
Name                    Source Score Preview
----                    ------ ----- -------
powershell-array-handling Serena 1.0   PowerShell arrays need @() f...
powershell-arrays        Serena 1.0   Common array operations incl...
```

#### Example 3: Limited Results

```bash
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 \
    -Query "authentication" \
    -MaxResults 3
```

#### Example 4: Semantic Search

```bash
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 \
    -Query "user login security" \
    -SemanticOnly
```

#### Example 5: From PowerShell Script

```powershell
$result = pwsh .claude/skills/memory/scripts/Search-Memory.ps1 `
    -Query "CI pipelines" `
    -MaxResults 5 | ConvertFrom-Json

foreach ($memory in $result.Results) {
    Write-Host "=== $($memory.Name) ==="
    Write-Host $memory.Content
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (see JSON output for details) |

### Dependencies

| Dependency | Required | Purpose |
|------------|----------|---------|
| PowerShell 7+ | Yes | Script execution |
| MemoryRouter.psm1 | Yes | Core search functionality |
| Serena MCP | Yes | Lexical memory search |
| Forgetful MCP | No | Semantic memory search |

### Validation

The skill validates input before processing:

1. **Query Length**: Must be 1-500 characters
2. **Query Characters**: Must match allowed pattern
3. **MaxResults Range**: Must be 1-100
4. **Format Value**: Must be Json or Table
5. **Module Existence**: MemoryRouter.psm1 must exist

### Error Handling

The skill handles errors gracefully:

```powershell
try {
    $results = Search-Memory @searchParams
    # ... output results
}
catch {
    $errorOutput = @{
        Error   = $_.Exception.Message
        Query   = $Query
        Details = $_.ScriptStackTrace
    }
    $errorOutput | ConvertTo-Json -Depth 3
    exit 1
}
```

### Security Considerations

1. **Input Validation**: Query is validated against a strict pattern to prevent injection
2. **No Shell Expansion**: Query is passed as-is, no variable expansion
3. **Sandboxed Execution**: Skill runs in PowerShell sandbox
4. **Read-Only**: Skill only reads memory, never writes

### Performance

| Metric | Typical Value |
|--------|---------------|
| Cold start | 100-200ms |
| Warm start | 50-100ms |
| Lexical search | 300-500ms |
| Semantic search | 500-1000ms |
| Combined search | 600-1200ms |

### Integration with Agent Workflows

#### Session Start Pattern

```powershell
# Per SESSION-PROTOCOL.md - search relevant context
$context = pwsh .claude/skills/memory/scripts/Search-Memory.ps1 `
    -Query "[session objectives]" `
    -MaxResults 10 | ConvertFrom-Json

if ($context.Count -gt 0) {
    Write-Host "Found $($context.Count) relevant memories"
    foreach ($result in $context.Results) {
        Write-Host "- $($result.Name): $($result.Content.Substring(0, 100))..."
    }
}
```

#### Pre-Decision Pattern

```powershell
# Before making technical decisions
$patterns = pwsh .claude/skills/memory/scripts/Search-Memory.ps1 `
    -Query "[decision topic] patterns" `
    -LexicalOnly | ConvertFrom-Json

$relevant = $patterns.Results | Where-Object {
    $_.Content -match "success|recommended|best practice"
}
```

#### Fallback Pattern

```powershell
# Try semantic, fall back to lexical
$result = pwsh .claude/skills/memory/scripts/Search-Memory.ps1 `
    -Query "[topic]" `
    -SemanticOnly 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Semantic search failed, using lexical"
    $result = pwsh .claude/skills/memory/scripts/Search-Memory.ps1 `
        -Query "[topic]" `
        -LexicalOnly
}
```

## Future Skills

The following skills are planned for future releases:

### Save-Memory.ps1 (Planned)

Store new memories to Serena with optional Forgetful sync.

### Query-Episodes.ps1 (Planned)

Search episodic memory for past session decisions.

### Trace-Causality.ps1 (Planned)

Find causal paths between decisions and outcomes.

## Related Documentation

- [Memory Router](memory-router.md) - Underlying module
- [Agent Integration](agent-integration.md) - Agent workflows
- [API Reference](api-reference.md) - Complete API
- [Quick Start](quick-start.md) - Common patterns
