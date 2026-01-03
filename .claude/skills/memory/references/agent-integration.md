# Agent Integration Guide

## Overview

This guide explains how AI agents integrate with the memory system. The memory system is designed to be consumed by agents through skills, direct module imports, and MCP tools.

## Integration Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     AI Agent (Claude)                        │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │   Task Agents  │  │  Orchestrator  │  │    Memory      │ │
│  │  (implementer, │  │     Agent      │  │     Agent      │ │
│  │   analyst...)  │  │                │  │                │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘ │
└──────────┼───────────────────┼───────────────────┼──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     Access Methods                           │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │  Skill Script  │  │  PowerShell    │  │   MCP Tools    │ │
│  │  Search-Memory │  │   Module       │  │  Serena/       │ │
│  │     .ps1       │  │   Import       │  │  Forgetful     │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘ │
└──────────┼───────────────────┼───────────────────┼──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Memory System                             │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                   Memory Router                         │ │
│  │              (Serena-first + Forgetful)                 │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │                 Reflexion Memory                        │ │
│  │           (Episodes + Causal Reasoning)                 │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Access Methods

### Method 1: Skill Script (Recommended for Agents)

The primary interface for agents is the Search-Memory skill:

```bash
# Basic search
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks"

# With options
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 \
    -Query "PowerShell arrays" \
    -MaxResults 5 \
    -Format Json
```

**Advantages**:

- Standardized interface
- Input validation
- JSON output for parsing
- Error handling with structured output

### Method 2: PowerShell Module Import

For complex workflows requiring multiple operations:

```powershell
# Import modules
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

# Search across tiers
$results = Search-Memory -Query "authentication" -MaxResults 10

# Access episodes
$episodes = Get-Episodes -Outcome "success" -Since (Get-Date).AddDays(-30)

# Query causal relationships
$path = Get-CausalPath -FromLabel "decision" -ToLabel "outcome"
```

**Advantages**:

- Full API access
- Multiple operations without subprocess overhead
- Direct object manipulation

### Method 3: MCP Tools (Direct)

For direct MCP tool access:

```python
# Serena (file-based, always available)
mcp__serena__list_memories()
mcp__serena__read_memory(memory_file_name="powershell-arrays")
mcp__serena__write_memory(memory_file_name="new-pattern", content="...")

# Forgetful (semantic search, requires service)
mcp__forgetful__execute_forgetful_tool("query_memory", {
    "query": "authentication patterns",
    "query_context": "looking for security best practices"
})
```

**Advantages**:

- Native Claude tool integration
- No subprocess required
- Direct semantic search capability

## Agent Workflows

### Workflow 1: Memory-First Decision Making

Per ADR-007, agents retrieve memory before reasoning:

```text
┌─────────────────────────────────────────────────────────────┐
│                    Agent Task Received                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Search Semantic Memory (Tier 1)                     │
│                                                              │
│  Search-Memory -Query "[task topic]" -MaxResults 10          │
│                                                              │
│  → Retrieves relevant facts, patterns, rules                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Review Episodic Memory (Tier 2)                     │
│                                                              │
│  Get-Episodes | Where-Object { $_.task -match "[topic]" }    │
│                                                              │
│  → Past decisions and their outcomes                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Check Causal Patterns (Tier 3)                      │
│                                                              │
│  Get-Patterns -MinSuccessRate 0.7                            │
│  Get-AntiPatterns -MaxSuccessRate 0.3                        │
│                                                              │
│  → Proven patterns to follow, anti-patterns to avoid         │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Execute with Full Context                           │
│                                                              │
│  Agent reasoning grounded in past learnings                  │
└─────────────────────────────────────────────────────────────┘
```

### Workflow 2: Learning from Sessions

At session end, extract and persist learnings:

```text
┌─────────────────────────────────────────────────────────────┐
│                    Session Complete                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Extract Episode                                     │
│                                                              │
│  pwsh scripts/Extract-SessionEpisode.ps1 \                   │
│      -SessionLogPath ".agents/sessions/[session].md"         │
│                                                              │
│  → Structured episode from session transcript                │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Update Causal Graph                                 │
│                                                              │
│  pwsh scripts/Update-CausalGraph.ps1                         │
│                                                              │
│  → New nodes and edges from episode decisions/outcomes       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Store Key Memories                                  │
│                                                              │
│  mcp__serena__write_memory(...)                              │
│  mcp__forgetful__execute_forgetful_tool("create_memory",...) │
│                                                              │
│  → Persist important patterns for future sessions            │
└─────────────────────────────────────────────────────────────┘
```

### Workflow 3: Failure Analysis

When investigating past failures:

```powershell
# 1. Find failed sessions
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-30)

# 2. Analyze each failure
foreach ($failure in $failures) {
    # Get decision sequence
    $decisions = Get-DecisionSequence -SessionId $failure.session

    # Find error events
    $errors = $failure.events | Where-Object { $_.type -eq "error" }

    # Check if recovery was attempted
    $recoveries = $decisions | Where-Object { $_.type -eq "recovery" }

    # Extract lessons for this failure
    Write-Host "Session: $($failure.session)"
    Write-Host "Lessons: $($failure.lessons -join '; ')"
}

# 3. Find common patterns in failures
$antiPatterns = Get-AntiPatterns -MaxSuccessRate 0.3
```

## Agent-Specific Integration

### Orchestrator Agent

The orchestrator uses memory to route tasks effectively:

```powershell
# Check for relevant past context
$context = Search-Memory -Query "[task description]" -MaxResults 5

# Review past similar task outcomes
$pastTasks = Get-Episodes | Where-Object {
    $_.task -match "[task keywords]"
}

# Determine if specialized agent needed based on patterns
$patterns = Get-Patterns | Where-Object {
    $_.trigger -match "[task type]"
}

# Route to appropriate agent with context
```

### Analyst Agent

The analyst uses episodic memory for investigation:

```powershell
# Research phase - gather all relevant memories
$knowledge = Search-Memory -Query "[investigation topic]" -MaxResults 20

# Look for past investigations
$investigations = Get-Episodes | Where-Object {
    $_.task -match "investigate|research|analyze"
}

# Trace causal relationships
$causalPath = Get-CausalPath -FromLabel "[cause]" -ToLabel "[effect]"

# Build analysis from historical context
```

### Implementer Agent

The implementer uses patterns to guide implementation:

```powershell
# Find relevant implementation patterns
$patterns = Get-Patterns -MinSuccessRate 0.8 | Where-Object {
    $_.action -match "[implementation type]"
}

# Check for anti-patterns to avoid
$antiPatterns = Get-AntiPatterns | Where-Object {
    $_.trigger -match "[implementation area]"
}

# Review past implementation decisions
$decisions = Get-Episodes | ForEach-Object {
    $_.decisions | Where-Object { $_.type -eq "implementation" }
}
```

### Retrospective Agent

The retrospective agent captures learnings:

```powershell
# Extract session episode
$episode = pwsh scripts/Extract-SessionEpisode.ps1 -SessionLogPath "[log]"

# Analyze decision outcomes
$decisionAnalysis = Get-DecisionSequence -SessionId "[session]" |
    Group-Object { $_.outcome } |
    Select-Object Name, Count

# Identify new patterns
$newPatterns = @()
foreach ($decision in $episode.decisions) {
    if ($decision.outcome -eq "success") {
        $newPatterns += @{
            trigger = $decision.rationale
            action = $decision.chosen
        }
    }
}

# Update causal graph
pwsh scripts/Update-CausalGraph.ps1 -EpisodePath "[episode]"

# Store extracted patterns
foreach ($pattern in $newPatterns) {
    Add-Pattern @pattern
}
```

## Session Protocol Integration

### Session Start

Per SESSION-PROTOCOL.md, agents MUST:

```powershell
# 1. Read mandatory memory (BLOCKING)
mcp__serena__read_memory(memory_file_name="usage-mandatory")

# 2. Search for relevant project context
Search-Memory -Query "[session objectives]" -MaxResults 10

# 3. Review recent episodes
Get-Episodes -Since (Get-Date).AddDays(-7) -MaxResults 5
```

### Session End

Per SESSION-PROTOCOL.md, agents MUST:

```powershell
# 1. Extract episode from session log
pwsh scripts/Extract-SessionEpisode.ps1 -SessionLogPath "[log]"

# 2. Update causal graph
pwsh scripts/Update-CausalGraph.ps1

# 3. Store cross-session context
mcp__serena__write_memory(memory_file_name="[relevant-memory]", content="...")

# 4. Commit changes
git add .agents/memory/ .serena/memories/
git commit -m "session: Extract episode and update memory"
```

## Best Practices

### For All Agents

1. **Memory First**: Always search memory before multi-step reasoning
2. **Check Patterns**: Review proven patterns before implementation
3. **Avoid Anti-Patterns**: Check failure patterns before risky operations
4. **Record Decisions**: Ensure session logs capture decision rationale
5. **Extract Learnings**: Always extract episodes at session end

### For Memory Queries

1. **Be Specific**: "PowerShell array handling" not "arrays"
2. **Use Filters**: Limit results to avoid information overload
3. **Check Availability**: Handle Forgetful unavailability gracefully
4. **Cache Results**: Reuse within a session to reduce latency

### For Episode Management

1. **Extract Immediately**: Don't delay episode extraction
2. **Update Graph**: Always update causal graph after extraction
3. **Verify Outcomes**: Ensure decisions have outcome tracking
4. **Store Lessons**: Make lessons actionable and specific

## Error Handling

### Forgetful Unavailable

```powershell
try {
    $results = Search-Memory -Query "[topic]" -SemanticOnly
}
catch {
    Write-Warning "Forgetful unavailable, using lexical search"
    $results = Search-Memory -Query "[topic]" -LexicalOnly
}
```

### Episode Not Found

```powershell
$episode = Get-Episode -SessionId "[session]"
if (-not $episode) {
    Write-Warning "Episode not found, extracting from session log"
    pwsh scripts/Extract-SessionEpisode.ps1 -SessionLogPath "[log]"
    $episode = Get-Episode -SessionId "[session]"
}
```

### Causal Graph Empty

```powershell
$status = Get-ReflexionMemoryStatus
if ($status.CausalGraph.Nodes -eq 0) {
    Write-Warning "Causal graph empty, rebuilding from episodes"
    Get-ChildItem ".agents/memory/episodes/*.json" | ForEach-Object {
        pwsh scripts/Update-CausalGraph.ps1 -EpisodePath $_.FullName
    }
}
```

## Performance Considerations

| Operation | Typical Latency | Notes |
|-----------|----------------|-------|
| Skill script invocation | 50-100ms | PowerShell startup |
| Search-Memory (lexical) | 300-500ms | File-based search |
| Search-Memory (semantic) | 500-1000ms | Depends on Forgetful |
| Get-Episodes | 100-200ms | File enumeration |
| Get-CausalPath | 50-100ms | In-memory graph |
| Episode extraction | 2-5s | Parsing and analysis |

### Optimization Tips

1. **Cache module imports**: Import once per session
2. **Use LexicalOnly for known terms**: Faster, no network
3. **Limit MaxResults**: Reduce processing overhead
4. **Batch episode queries**: Use Get-Episodes instead of multiple Get-Episode

## Related Documentation

- [README.md](README.md) - System overview
- [Quick Start](quick-start.md) - Common patterns
- [API Reference](api-reference.md) - Complete function signatures
- [Skill Reference](skill-reference.md) - Skill script documentation
- ADR-007 - Memory-First Architecture
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
