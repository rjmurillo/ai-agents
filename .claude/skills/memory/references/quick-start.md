# Memory System Quick Start Guide

## Overview

This guide provides common usage patterns for the ai-agents memory system (v0.2.0). Follow these examples to get started quickly.

## For AI Agents

### Basic Memory Search

```powershell
# Import the Memory Router
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1

# Search for relevant knowledge before making decisions
$results = Search-Memory -Query "PowerShell array handling" -MaxResults 5

# Process results
foreach ($result in $results) {
    Write-Host "=== $($result.Name) (Source: $($result.Source)) ==="
    Write-Host $result.Content
    Write-Host ""
}
```

**Use When**: Starting any non-trivial task, before making technical decisions.

### Agent Workflow Example

```powershell
# 1. Search memory for relevant patterns
$arrayPatterns = Search-Memory -Query "PowerShell arrays" -MaxResults 5

# 2. Review past failures in similar scenarios
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1
$pastFailures = Get-Episodes -Outcome "failure" | Where-Object {
    $_.task -match "PowerShell" -or $_.task -match "array"
}

# 3. Check for known patterns
$patterns = Get-Patterns -MinSuccessRate 0.7 -MinOccurrences 2

# 4. Make informed decision based on memory
# ... your agent logic here ...
```

### Check for Anti-Patterns

```powershell
# Before implementing a solution, check for known anti-patterns
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

$antiPatterns = Get-AntiPatterns -MaxSuccessRate 0.3

foreach ($ap in $antiPatterns) {
    Write-Host "AVOID: $($ap.name)"
    Write-Host "  Failure rate: $((1 - $ap.success_rate) * 100)%"
    Write-Host "  Trigger: $($ap.trigger)"
    Write-Host ""
}
```

## For Human Users

### Search via Skill Script

```bash
# Basic search with JSON output
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 \
    -Query "git hooks" \
    -Format Json

# Table format for quick review
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 \
    -Query "session protocol" \
    -Format Table
```

### Check System Status

```bash
# Run comprehensive health check (recommended)
pwsh .claude/skills/memory/scripts/Test-MemoryHealth.ps1 -Format Table

# Memory Router status
pwsh -c "Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1; Get-MemoryRouterStatus | ConvertTo-Json"

# Reflexion Memory status
pwsh -c "Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1; Get-ReflexionMemoryStatus | ConvertTo-Json"
```

### Extract Episode from Session

```bash
# After completing a session
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 \
    -SessionLogPath ".agents/sessions/.agents/sessions/2026-01-01-session-130.json"

# Update causal graph
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1
```

## Common Patterns

### Pattern 1: Memory-First Decision Making

```powershell
# Import both modules
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

# Step 1: Search for relevant knowledge
$knowledge = Search-Memory -Query "topic" -MaxResults 5

# Step 2: Check for proven patterns
$patterns = Get-Patterns -MinSuccessRate 0.7 | Where-Object {
    $_.trigger -match "topic" -or $_.action -match "topic"
}

# Step 3: Review past attempts
$pastAttempts = Get-Episodes | Where-Object { $_.task -match "topic" }

# Step 4: Make decision with full context
# ... decision logic ...

# Step 5: Record decision in episode (at session end)
```

### Pattern 2: Failure Analysis

```powershell
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

# Get recent failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-30)

foreach ($failure in $failures) {
    Write-Host "`n=== $($failure.session) ==="
    Write-Host "Task: $($failure.task)"

    # Extract lessons
    Write-Host "`nLessons:"
    foreach ($lesson in $failure.lessons) {
        Write-Host "  - $lesson"
    }

    # Find error events
    $errors = $failure.events | Where-Object { $_.type -eq "error" }
    if ($errors) {
        Write-Host "`nErrors:"
        foreach ($err in $errors) {
            Write-Host "  - $($err.content)"
        }
    }

    # Find recovery decisions
    $recoveries = $failure.decisions | Where-Object { $_.type -eq "recovery" }
    if ($recoveries) {
        Write-Host "`nRecoveries Attempted:"
        foreach ($rec in $recoveries) {
            Write-Host "  - $($rec.chosen) (Outcome: $($rec.outcome))"
        }
    }
}
```

### Pattern 3: Pattern Library Maintenance

```powershell
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

# Get all patterns
$allPatterns = Get-Patterns

# Categorize by success rate
$highSuccess = $allPatterns | Where-Object { $_.success_rate -ge 0.8 }
$mediumSuccess = $allPatterns | Where-Object { $_.success_rate -ge 0.5 -and $_.success_rate -lt 0.8 }
$lowSuccess = $allPatterns | Where-Object { $_.success_rate -lt 0.5 }

Write-Host "=== Pattern Library Summary ==="
Write-Host "High Success (≥80%): $($highSuccess.Count)"
Write-Host "Medium Success (50-79%): $($mediumSuccess.Count)"
Write-Host "Low Success (<50%): $($lowSuccess.Count)"

# Review low success patterns for archival
foreach ($pattern in $lowSuccess) {
    Write-Host "`n$($pattern.name):"
    Write-Host "  Success: $($pattern.success_rate * 100)%"
    Write-Host "  Uses: $($pattern.occurrences)"
    Write-Host "  Consider: Archival or revision"
}
```

### Pattern 4: Causal Tracing

```powershell
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1

# Find causal path from decision to outcome
$path = Get-CausalPath `
    -FromLabel "routing strategy" `
    -ToLabel "performance target met" `
    -MaxDepth 5

if ($path.found) {
    Write-Host "Causal chain ($($path.depth) steps):"
    for ($i = 0; $i -lt $path.path.Count; $i++) {
        $node = $path.path[$i]
        Write-Host "  $($i + 1). $($node.label) ($($node.type))"

        # Show success rate
        if ($node.success_rate) {
            Write-Host "     Success rate: $($node.success_rate * 100)%"
        }
    }
}
else {
    Write-Host "No causal path found: $($path.error)"
}
```

### Pattern 5: Session End Workflow

```powershell
# Complete at end of every session

# 1. Extract episode from session log
$sessionId = "2026-01-01-session-130"
$sessionLog = ".agents/sessions/$sessionId.md"

pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 -SessionLogPath $sessionLog

# 2. Update causal graph
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1 -EpisodePath ".agents/memory/episodes/episode-$sessionId.json"

# 3. Verify extraction
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1
$episode = Get-Episode -SessionId $sessionId

Write-Host "Episode verified:"
Write-Host "  Outcome: $($episode.outcome)"
Write-Host "  Decisions: $($episode.decisions.Count)"
Write-Host "  Events: $($episode.events.Count)"
Write-Host "  Lessons: $($episode.lessons.Count)"

# 4. Check causal graph update
$status = Get-ReflexionMemoryStatus
Write-Host "`nCausal graph:"
Write-Host "  Nodes: $($status.CausalGraph.Nodes)"
Write-Host "  Edges: $($status.CausalGraph.Edges)"
Write-Host "  Patterns: $($status.CausalGraph.Patterns)"
```

## Integration with Session Protocol

### Session Start

```powershell
# Required step in SESSION-PROTOCOL.md

# 1. Read usage-mandatory memory
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1
$mandatory = Search-Memory -Query "usage-mandatory" -LexicalOnly

# 2. Search for relevant project memories
$projectContext = Search-Memory -Query "project phase 2A" -MaxResults 10

# 3. Review recent episodes
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1
$recentEpisodes = Get-Episodes -Since (Get-Date).AddDays(-7) -MaxResults 5

# Now proceed with session work...
```

### Session End

```powershell
# Required step in SESSION-PROTOCOL.md

# 1. Extract episode
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 \
    -SessionLogPath ".agents/sessions/$(Get-Date -Format 'yyyy-MM-dd')-session-*.md"

# 2. Update causal graph
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1

# 3. Commit changes (including episodes and causality)
git add .agents/memory/episodes/ .agents/memory/causality/
git commit -m "session: Extract episode and update causal graph"
```

## Performance Optimization

### When to Use LexicalOnly

```powershell
# Use LexicalOnly when:
# - Forgetful is unavailable
# - Performance is critical
# - Exact keyword matching is needed

$results = Search-Memory -Query "exact term" -LexicalOnly
```

### When to Use SemanticOnly

```powershell
# Use SemanticOnly when:
# - Need conceptual similarity
# - Keywords are ambiguous
# - Exploring related topics

try {
    $results = Search-Memory -Query "authentication security" -SemanticOnly
}
catch {
    Write-Warning "Forgetful unavailable, falling back to lexical"
    $results = Search-Memory -Query "authentication security" -LexicalOnly
}
```

### Caching Results

```powershell
# Cache frequently accessed memories in session
$script:MemoryCache = @{}

function Get-CachedMemory {
    param([string]$Query)

    if (-not $script:MemoryCache.ContainsKey($Query)) {
        $script:MemoryCache[$Query] = Search-Memory -Query $Query
    }

    return $script:MemoryCache[$Query]
}

# Use cached results
$results = Get-CachedMemory -Query "PowerShell arrays"
```

## Troubleshooting

### No Results from Search

```powershell
# Check system status first
$status = Get-MemoryRouterStatus

if (-not $status.Serena.Available) {
    Write-Error "Serena not available at: $($status.Serena.Path)"
}

# Verify memory files exist
$memoryCount = (Get-ChildItem $status.Serena.Path -Filter "*.md").Count
Write-Host "Memory files: $memoryCount"

# Try broader query
$results = Search-Memory -Query "PowerShell" -MaxResults 20
```

### Episode Not Found

```powershell
# Check if episode file exists
$episodePath = ".agents/memory/episodes/episode-2026-01-01-session-126.json"
if (-not (Test-Path $episodePath)) {
    Write-Warning "Episode not extracted yet"

    # Extract from session log
    $sessionLog = ".agents/sessions/.agents/sessions/2026-01-01-session-126.json"
    if (Test-Path $sessionLog) {
        pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 -SessionLogPath $sessionLog
    }
}
```

### Forgetful Not Available

```powershell
# Check Forgetful health
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1

$available = Test-ForgetfulAvailable -Force

if (-not $available) {
    Write-Warning "Forgetful not available"
    Write-Host "Solutions:"
    Write-Host "  1. Start Forgetful: systemctl --user start forgetful"
    Write-Host "  2. Check port: netstat -an | grep 8020"
    Write-Host "  3. Use -LexicalOnly: Search-Memory -Query 'test' -LexicalOnly"
}
```

## Best Practices

### For Agents

1. **Always search before deciding**: Use `Search-Memory` at task start
2. **Check patterns**: Use `Get-Patterns` to find proven approaches
3. **Avoid anti-patterns**: Use `Get-AntiPatterns` before implementing
4. **Learn from failures**: Query past failures for similar scenarios
5. **Record decisions**: Ensure episodes capture decision rationale

### For Session Management

1. **Extract episodes immediately**: Don't delay until later sessions
2. **Update causal graph regularly**: Run after each episode extraction
3. **Review patterns weekly**: Check for new high-success patterns
4. **Prune stale data**: Archive low-frequency nodes periodically
5. **Commit with context**: Include episode/graph updates in session commits

### For Memory Queries

1. **Use specific queries**: "PowerShell array handling" not "arrays"
2. **Limit results**: Use `-MaxResults` to avoid information overload
3. **Try both modes**: Compare lexical vs semantic for ambiguous queries
4. **Cache frequent queries**: Reuse results within a session
5. **Check availability**: Use `Get-MemoryRouterStatus` if queries fail

## Examples by Use Case

### Use Case: Implementing New Feature

```powershell
# 1. Search for similar features
$similar = Search-Memory -Query "feature implementation patterns" -MaxResults 10

# 2. Check proven design patterns
$patterns = Get-Patterns -MinSuccessRate 0.8 | Where-Object {
    $_.trigger -match "design" -or $_.action -match "architecture"
}

# 3. Review past feature implementations
$pastFeatures = Get-Episodes | Where-Object {
    $_.task -match "implement" -and $_.outcome -eq "success"
}

# 4. Implement with full context
# ... implementation ...
```

### Use Case: Debugging Issue

```powershell
# 1. Search for error patterns
$errorPatterns = Search-Memory -Query "error message text" -MaxResults 5

# 2. Find past similar errors
$pastErrors = Get-Episodes | Where-Object {
    $_.events | Where-Object { $_.type -eq "error" -and $_.content -match "error pattern" }
}

# 3. Check recovery patterns
$recoveries = Get-Patterns | Where-Object { $_.trigger -match "error pattern" }

# 4. Apply recovery strategy
# ... debugging ...
```

### Use Case: Code Review

```powershell
# 1. Search for coding standards
$standards = Search-Memory -Query "PowerShell code style" -MaxResults 5

# 2. Check for anti-patterns in code
$antiPatterns = Get-AntiPatterns

# 3. Review past code review findings
$pastReviews = Get-Episodes | Where-Object {
    $_.task -match "review" -and $_.lessons.Count -gt 0
}

# 4. Perform review with context
# ... review ...
```

## Additional Resources

- [Full API Reference](api-reference.md) - Complete function signatures
- [Memory Router Documentation](memory-router.md) - Detailed Router usage
- [Reflexion Memory Documentation](reflexion-memory.md) - Detailed Reflexion usage
- [Benchmarking Guide](benchmarking.md) - Performance measurement
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
