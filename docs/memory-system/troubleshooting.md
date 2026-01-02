# Memory System Troubleshooting Guide

## Overview

This guide provides solutions to common issues with the memory system. Issues are organized by component and symptom.

## Quick Diagnostics

### System Status Check

Run these commands to quickly assess system health:

```powershell
# Memory Router status
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1
Get-MemoryRouterStatus | ConvertTo-Json -Depth 3

# Reflexion Memory status
Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1
Get-ReflexionMemoryStatus | ConvertTo-Json -Depth 3

# Forgetful health check
pwsh scripts/forgetful/Test-ForgetfulHealth.ps1
```

### Expected Healthy Output

```json
{
  "SerenaAvailable": true,
  "ForgetfulAvailable": true,
  "SerenaPath": "/path/to/.serena/memories",
  "SerenaMemoryCount": 460,
  "ForgetfulUrl": "http://localhost:8020"
}
```

## Memory Router Issues

### Issue: No Results from Search

**Symptoms**:

- `Search-Memory` returns empty results
- Expected memories not found

**Diagnosis**:

```powershell
# Check system status
$status = Get-MemoryRouterStatus

# Verify Serena path exists
Test-Path $status.SerenaPath

# Count memories
(Get-ChildItem $status.SerenaPath -Filter "*.md").Count

# Try exact filename match
Get-ChildItem $status.SerenaPath -Filter "*keyword*"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Serena path incorrect | Verify `.serena/memories/` exists |
| No memories created yet | Create initial memories |
| Query too specific | Try broader search terms |
| Special characters in query | Use only alphanumeric + allowed punctuation |

### Issue: Forgetful Not Available

**Symptoms**:

- `ForgetfulAvailable: false` in status
- Semantic search fails
- Error: "Connection refused"

**Diagnosis**:

```powershell
# Check if Forgetful is running
pwsh scripts/forgetful/Test-ForgetfulHealth.ps1

# Check port
Test-NetConnection -ComputerName localhost -Port 8020

# Check service (Linux)
systemctl --user status forgetful

# Check service (Windows)
Get-ScheduledTask -TaskName 'ForgetfulMCP' | Get-ScheduledTaskInfo
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Service not running | Start Forgetful service |
| Wrong port | Verify port 8020 in configuration |
| Service crashed | Restart service, check logs |
| Network issue | Verify localhost connectivity |

**Starting Forgetful**:

```bash
# Linux
systemctl --user start forgetful

# Windows
Start-ScheduledTask -TaskName 'ForgetfulMCP'

# Manual (any OS)
cd path/to/forgetful && python -m forgetful serve --port 8020
```

### Issue: Query Validation Error

**Symptoms**:

- Error: "Cannot validate argument on parameter 'Query'"
- Query rejected before search

**Diagnosis**:

```powershell
# Check query against pattern
$query = "your query here"
$pattern = '^[a-zA-Z0-9\s\-.,_()&:]+$'
$query -match $pattern  # Should return True
```

**Solutions**:

| Invalid Character | Fix |
|-------------------|-----|
| `<` `>` | Remove or replace |
| `'` `"` | Remove or replace with word |
| `$` `@` | Remove |
| `!` `?` | Remove |
| `\` `/` | Use space or hyphen |

**Valid Query Examples**:

```text
"PowerShell arrays"                    # Spaces OK
"git hooks: pre-commit"               # Colons OK
"authentication (OAuth 2.0)"          # Parentheses OK
"CI-CD pipelines"                     # Hyphens OK
```

### Issue: Slow Search Performance

**Symptoms**:

- Searches take >2 seconds
- Timeouts during search

**Diagnosis**:

```powershell
# Benchmark search
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$results = Search-Memory -Query "test" -LexicalOnly
$sw.Stop()
Write-Host "Lexical: $($sw.ElapsedMilliseconds)ms"

$sw.Restart()
$results = Search-Memory -Query "test" -SemanticOnly
$sw.Stop()
Write-Host "Semantic: $($sw.ElapsedMilliseconds)ms"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Too many memories | Archive old memories |
| Forgetful slow | Check Forgetful logs, restart |
| File system slow | Check disk I/O |
| Large memory files | Split into smaller memories |

**Performance Targets**:

| Operation | Target |
|-----------|--------|
| Lexical search | <500ms |
| Semantic search | <1000ms |
| Combined search | <1200ms |

## Reflexion Memory Issues

### Issue: Episode Not Found

**Symptoms**:

- `Get-Episode` returns null
- Error: "Episode not found for session"

**Diagnosis**:

```powershell
# Check episode file exists
$sessionId = "2026-01-01-session-130"
$episodePath = ".agents/memory/episodes/episode-$sessionId.json"
Test-Path $episodePath

# List available episodes
Get-ChildItem ".agents/memory/episodes" -Filter "*.json" | Select-Object Name

# Check session log exists
Test-Path ".agents/sessions/$sessionId.md"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Episode not extracted | Run Extract-SessionEpisode.ps1 |
| Wrong session ID format | Use format: YYYY-MM-DD-session-NNN |
| Episode directory missing | Create `.agents/memory/episodes/` |

**Extracting Episode**:

```powershell
pwsh scripts/Extract-SessionEpisode.ps1 `
    -SessionLogPath ".agents/sessions/2026-01-01-session-130.md"
```

### Issue: Causal Graph Empty

**Symptoms**:

- `Get-Patterns` returns empty
- `Get-CausalPath` returns "No path found"
- `CausalGraph.Nodes: 0` in status

**Diagnosis**:

```powershell
# Check causal graph file
$graphPath = ".agents/memory/causality/causal-graph.json"
Test-Path $graphPath

# Check graph content
if (Test-Path $graphPath) {
    $graph = Get-Content $graphPath | ConvertFrom-Json
    Write-Host "Nodes: $($graph.nodes.Count)"
    Write-Host "Edges: $($graph.edges.Count)"
    Write-Host "Patterns: $($graph.patterns.Count)"
}

# Check if episodes exist
(Get-ChildItem ".agents/memory/episodes" -Filter "*.json").Count
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| No episodes extracted | Extract episodes first |
| Graph never built | Run Update-CausalGraph.ps1 |
| Graph file corrupted | Delete and rebuild |

**Rebuilding Causal Graph**:

```powershell
# Remove old graph
Remove-Item ".agents/memory/causality/causal-graph.json" -ErrorAction SilentlyContinue

# Rebuild from all episodes
Get-ChildItem ".agents/memory/episodes/*.json" | ForEach-Object {
    pwsh scripts/Update-CausalGraph.ps1 -EpisodePath $_.FullName
}
```

### Issue: Episode Extraction Fails

**Symptoms**:

- Extract-SessionEpisode.ps1 errors
- Incomplete or empty episodes

**Diagnosis**:

```powershell
# Check session log exists and has content
$logPath = ".agents/sessions/2026-01-01-session-130.md"
if (Test-Path $logPath) {
    $content = Get-Content $logPath -Raw
    Write-Host "Log size: $($content.Length) chars"
    Write-Host "Has decisions: $($content -match '## Decisions')"
    Write-Host "Has outcome: $($content -match '## (Outcome|Result)')"
}
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Session log incomplete | Complete session log with all sections |
| Missing required sections | Add Decisions and Outcome sections |
| Malformed markdown | Fix markdown syntax |
| Encoding issues | Save as UTF-8 |

**Required Session Log Sections**:

```markdown
## Session: 2026-01-01-session-130

## Objective
[What the session aimed to accomplish]

## Decisions
[List of decisions made during session]

## Events
[Notable events: errors, milestones, commits]

## Outcome
[success|partial|failure with explanation]

## Lessons Learned
[Key takeaways from the session]
```

### Issue: Pattern Not Recognized

**Symptoms**:

- Expected patterns not in `Get-Patterns` output
- Success rate shows 0 when should be higher

**Diagnosis**:

```powershell
# Check pattern in graph
$graph = Get-Content ".agents/memory/causality/causal-graph.json" | ConvertFrom-Json
$graph.patterns | Where-Object { $_.name -match "pattern name" }

# Check related nodes
$graph.nodes | Where-Object { $_.label -match "decision keyword" }

# Check edges
$graph.edges | Where-Object { $_.from -match "decision" }
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Pattern threshold not met | Pattern needs MinOccurrences (default 3) |
| Episodes not processed | Run Update-CausalGraph.ps1 |
| Decision not recorded | Ensure session logs capture decisions |

## Skill Issues

### Issue: Skill Script Not Found

**Symptoms**:

- Error: "Cannot find path"
- Skill invocation fails

**Diagnosis**:

```powershell
# Verify skill location
Test-Path ".claude/skills/memory/scripts/Search-Memory.ps1"

# List available skills
Get-ChildItem ".claude/skills" -Recurse -Filter "*.ps1"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Wrong path | Use correct relative path from project root |
| Skill not installed | Verify skill directory structure |
| Permissions issue | Check file permissions |

### Issue: Module Import Failure

**Symptoms**:

- Error: "MemoryRouter module not found"
- Import-Module fails

**Diagnosis**:

```powershell
# Check module path
$modulePath = ".claude/skills/memory/scripts/MemoryRouter.psm1"
Test-Path $modulePath

# Test import
Import-Module $modulePath -Force -Verbose
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Wrong working directory | Run from project root |
| Module file missing | Verify .claude/skills/memory/scripts/ directory |
| Syntax error in module | Check PowerShell syntax |

## Directory Structure Issues

### Issue: Memory Directories Missing

**Symptoms**:

- Error: "Directory not found"
- Episode/causality operations fail

**Diagnosis**:

```powershell
# Check required directories
$dirs = @(
    ".serena/memories",
    ".agents/memory/episodes",
    ".agents/memory/causality"
)

foreach ($dir in $dirs) {
    $exists = Test-Path $dir
    Write-Host "$dir : $exists"
}
```

**Solutions**:

Create missing directories:

```powershell
New-Item -ItemType Directory -Force -Path ".serena/memories"
New-Item -ItemType Directory -Force -Path ".agents/memory/episodes"
New-Item -ItemType Directory -Force -Path ".agents/memory/causality"
```

### Issue: Path Mismatch After Migration

**Symptoms**:

- Scripts reference old paths
- Tests fail with path errors

**Diagnosis**:

```powershell
# Check for old path references
Get-ChildItem -Path "scripts", "tests" -Filter "*.ps1" -Recurse |
    Select-String -Pattern '\.agents/episodes[^/]|\.agents/causality[^/]'
```

**Solutions**:

Update all references to use new paths:

```text
Old Path                    New Path
.agents/episodes/           .agents/memory/episodes/
.agents/causality/          .agents/memory/causality/
```

## Common Error Messages

### "Cannot validate argument on parameter 'Query'"

**Cause**: Query contains invalid characters.

**Fix**: Use only allowed characters: `a-zA-Z0-9\s\-.,_()&:`

### "Connection refused to localhost:8020"

**Cause**: Forgetful MCP server not running.

**Fix**: Start Forgetful service or use `-LexicalOnly` switch.

### "Episode not found for session"

**Cause**: Episode not extracted from session log.

**Fix**: Run `Extract-SessionEpisode.ps1` on the session log.

### "No causal path found"

**Cause**: No causal relationship exists between nodes.

**Fix**: Verify nodes exist, check edge directions, increase depth.

### "Memory file not found"

**Cause**: Serena memory file doesn't exist.

**Fix**: Create memory or check filename spelling.

## Diagnostic Scripts

### Full System Check

```powershell
# Save as Check-MemorySystem.ps1
[CmdletBinding()]
param()

Write-Host "=== Memory System Diagnostic ===" -ForegroundColor Cyan

# Check directories
Write-Host "`n[Directories]" -ForegroundColor Yellow
@(
    ".serena/memories",
    ".agents/memory/episodes",
    ".agents/memory/causality"
) | ForEach-Object {
    $exists = Test-Path $_
    $status = if ($exists) { "OK" } else { "MISSING" }
    $color = if ($exists) { "Green" } else { "Red" }
    Write-Host "  $_ : $status" -ForegroundColor $color
}

# Check modules
Write-Host "`n[Modules]" -ForegroundColor Yellow
@(
    ".claude/skills/memory/scripts/MemoryRouter.psm1",
    ".claude/skills/memory/scripts/ReflexionMemory.psm1"
) | ForEach-Object {
    $exists = Test-Path $_
    $status = if ($exists) { "OK" } else { "MISSING" }
    $color = if ($exists) { "Green" } else { "Red" }
    Write-Host "  $_ : $status" -ForegroundColor $color
}

# Check Serena memories
Write-Host "`n[Serena Memories]" -ForegroundColor Yellow
if (Test-Path ".serena/memories") {
    $count = (Get-ChildItem ".serena/memories" -Filter "*.md").Count
    Write-Host "  Count: $count" -ForegroundColor Green
} else {
    Write-Host "  Directory missing" -ForegroundColor Red
}

# Check episodes
Write-Host "`n[Episodes]" -ForegroundColor Yellow
if (Test-Path ".agents/memory/episodes") {
    $count = (Get-ChildItem ".agents/memory/episodes" -Filter "*.json").Count
    Write-Host "  Count: $count" -ForegroundColor Green
} else {
    Write-Host "  Directory missing" -ForegroundColor Red
}

# Check causal graph
Write-Host "`n[Causal Graph]" -ForegroundColor Yellow
$graphPath = ".agents/memory/causality/causal-graph.json"
if (Test-Path $graphPath) {
    $graph = Get-Content $graphPath | ConvertFrom-Json
    Write-Host "  Nodes: $($graph.nodes.Count)" -ForegroundColor Green
    Write-Host "  Edges: $($graph.edges.Count)" -ForegroundColor Green
    Write-Host "  Patterns: $($graph.patterns.Count)" -ForegroundColor Green
} else {
    Write-Host "  Graph not found" -ForegroundColor Red
}

# Check Forgetful
Write-Host "`n[Forgetful]" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8020/health" -TimeoutSec 2
    Write-Host "  Status: Available" -ForegroundColor Green
} catch {
    Write-Host "  Status: Unavailable" -ForegroundColor Yellow
    Write-Host "  (System works via Serena fallback)" -ForegroundColor Gray
}

Write-Host "`n=== Diagnostic Complete ===" -ForegroundColor Cyan
```

### Search Performance Test

```powershell
# Save as Test-SearchPerformance.ps1
[CmdletBinding()]
param(
    [string[]]$Queries = @("PowerShell", "git hooks", "authentication"),
    [int]$Iterations = 3
)

Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1

foreach ($query in $Queries) {
    Write-Host "`nQuery: '$query'" -ForegroundColor Cyan

    # Lexical only
    $times = @()
    for ($i = 0; $i -lt $Iterations; $i++) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $null = Search-Memory -Query $query -LexicalOnly
        $sw.Stop()
        $times += $sw.ElapsedMilliseconds
    }
    $avg = ($times | Measure-Object -Average).Average
    Write-Host "  Lexical: $([int]$avg)ms avg" -ForegroundColor Yellow

    # Combined (if Forgetful available)
    $status = Get-MemoryRouterStatus
    if ($status.ForgetfulAvailable) {
        $times = @()
        for ($i = 0; $i -lt $Iterations; $i++) {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $null = Search-Memory -Query $query
            $sw.Stop()
            $times += $sw.ElapsedMilliseconds
        }
        $avg = ($times | Measure-Object -Average).Average
        Write-Host "  Combined: $([int]$avg)ms avg" -ForegroundColor Yellow
    }
}
```

## Getting Help

If issues persist after trying these solutions:

1. **Check Logs**: Review session logs for error context
2. **Verify Configuration**: Ensure ADR-037 and ADR-038 guidelines are followed
3. **Review Documentation**: See [API Reference](api-reference.md) for function details
4. **File Issue**: Create GitHub issue with `memory-system` label

## Related Documentation

- [README.md](README.md) - System overview
- [API Reference](api-reference.md) - Complete function signatures
- [Quick Start](quick-start.md) - Common patterns
- [Benchmarking](benchmarking.md) - Performance measurement
