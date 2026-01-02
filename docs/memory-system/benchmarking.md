# Memory System Benchmarking

## Overview

Memory search performance benchmarking tool for measuring Serena (lexical) and Forgetful (semantic) search latency.

**Script**: `scripts/Measure-MemoryPerformance.ps1`

**Task**: M-008 (Phase 2A Memory System)

**Target**: 96-164x performance vs claude-flow baseline for equivalent operations

## Quick Start

```bash
# Run default benchmarks (8 queries, 5 iterations each)
pwsh scripts/Measure-MemoryPerformance.ps1

# Custom queries with more iterations
pwsh scripts/Measure-MemoryPerformance.ps1 \
    -Queries @("PowerShell arrays", "git hooks") \
    -Iterations 10

# Markdown report for documentation
pwsh scripts/Measure-MemoryPerformance.ps1 -Format markdown > benchmark-report.md

# JSON output for programmatic analysis
pwsh scripts/Measure-MemoryPerformance.ps1 -Format json | ConvertFrom-Json
```

## Usage

### Basic Benchmarking

```powershell
# Import not required - script is self-contained
pwsh scripts/Measure-MemoryPerformance.ps1

# Console output shows progress and results:
# === Memory Performance Benchmark (M-008) ===
# Queries: 8, Iterations: 5, Warmup: 2
#
# Benchmarking Serena (lexical search)...
#   Query: 'PowerShell array handling patterns'
#     Total: 532.45ms (List: 12.3ms, Match: 8.7ms, Read: 511.2ms)
#     Matched: 3 of 462 files
#   ...
#
# === Summary ===
# Serena Average: 530.12ms
# Forgetful Average: 245.67ms
# Speedup Factor: 2.16x
# Target: 96-164x (claude-flow baseline)
```

### Custom Queries

```powershell
# Define domain-specific queries
$queries = @(
    "PowerShell module patterns"
    "Git pre-commit validation"
    "Agent coordination protocols"
    "Memory-first architecture"
)

pwsh scripts/Measure-MemoryPerformance.ps1 -Queries $queries -Iterations 10
```

### Serena-Only Testing

```powershell
# Skip Forgetful benchmarks (useful when MCP unavailable)
pwsh scripts/Measure-MemoryPerformance.ps1 -SerenaOnly
```

### Output Formats

#### Console (Default)

Colored, human-readable output with progress indicators:

```text
=== Memory Performance Benchmark (M-008) ===
Queries: 8, Iterations: 5, Warmup: 2

Benchmarking Serena (lexical search)...
  Query: 'PowerShell array handling patterns'
    Total: 532.45ms (List: 12.3ms, Match: 8.7ms, Read: 511.2ms)
    Matched: 3 of 462 files

=== Summary ===
Serena Average: 530.12ms
Forgetful Average: 245.67ms
Speedup Factor: 2.16x
Target: 96-164x (claude-flow baseline)
```

#### Markdown

Structured report for documentation:

```markdown
# Memory Performance Benchmark Report

**Date**: 2026-01-01 17:30
**Task**: M-008 (Phase 2A Memory System)

## Configuration

| Setting | Value |
|---------|-------|
| Queries | 8 |
| Iterations | 5 |
| Warmup | 2 |

## Results

| System | Average (ms) | Status |
|--------|-------------|--------|
| Serena | 530.12 | Baseline |
| Forgetful | 245.67 | Below Target |

**Speedup Factor**: 2.16x
**Target**: 96-164x (claude-flow baseline)
```

#### JSON

Programmatic output for analysis:

```json
{
  "Timestamp": "2026-01-01T17:30:00Z",
  "Configuration": {
    "Queries": 8,
    "Iterations": 5,
    "WarmupIterations": 2,
    "SerenaPath": ".serena/memories",
    "ForgetfulEndpoint": "http://localhost:8020/mcp"
  },
  "SerenaResults": [
    {
      "Query": "PowerShell array handling patterns",
      "System": "Serena",
      "ListTimeMs": 12.3,
      "MatchTimeMs": 8.7,
      "ReadTimeMs": 511.2,
      "TotalTimeMs": 532.45,
      "MatchedFiles": 3,
      "TotalFiles": 462,
      "IterationTimes": [530.1, 535.2, 531.8, 533.0, 532.1]
    }
  ],
  "ForgetfulResults": [...],
  "Summary": {
    "SerenaAvgMs": 530.12,
    "ForgetfulAvgMs": 245.67,
    "SpeedupFactor": 2.16,
    "Target": "96-164x (claude-flow baseline)"
  }
}
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Queries | String[] | Default set | Array of test queries to benchmark |
| Iterations | Int32 | 5 | Number of iterations per query for averaging |
| WarmupIterations | Int32 | 2 | Number of warmup iterations before measurement |
| SerenaOnly | Switch | - | Only benchmark Serena (skip Forgetful) |
| Format | String | console | Output format: console, markdown, json |

### Default Query Set

The script includes 8 default queries covering different domains:

```powershell
@(
    "PowerShell array handling patterns"
    "git pre-commit hook validation"
    "GitHub CLI PR operations"
    "session protocol compliance"
    "security vulnerability detection"
    "Pester test isolation"
    "CI workflow patterns"
    "memory-first architecture"
)
```

**Rationale**: Diverse query set tests different keyword densities and result sizes.

## Metrics

### Serena Metrics

| Metric | Description | Typical Range |
|--------|-------------|---------------|
| ListTimeMs | Time to enumerate `.md` files in `.serena/memories/` | 10-20ms |
| MatchTimeMs | Time to match keywords against file names | 5-15ms |
| ReadTimeMs | Time to read matched file contents | 400-600ms |
| TotalTimeMs | Total search latency (sum of above) | 450-650ms |
| MatchedFiles | Number of files matching keywords | 0-20 |
| TotalFiles | Total files in memory directory | 460+ |

### Forgetful Metrics

| Metric | Description | Typical Range |
|--------|-------------|---------------|
| SearchTimeMs | HTTP roundtrip + embedding + vector search | 200-400ms |
| TotalTimeMs | Same as SearchTimeMs (single operation) | 200-400ms |
| MatchedMemories | Number of semantic matches returned | 0-10 |

### Summary Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| SerenaAvgMs | Average Serena search latency | 530ms (baseline) |
| ForgetfulAvgMs | Average Forgetful search latency | <100ms (goal) |
| SpeedupFactor | Serena / Forgetful ratio | >10x (goal) |

## Measurement Methodology

### Warmup Phase

Warmup iterations run before measurement to:

- Populate file system caches
- Warm up Forgetful embedding model
- Establish network connections
- Stabilize CPU frequency scaling

**Default**: 2 warmup iterations (not measured)

### Measurement Phase

Each query is executed multiple times (default: 5 iterations):

1. **Serena**:
   - List all memory files
   - Match keywords against filenames
   - Read matched file contents
   - Calculate total latency

2. **Forgetful** (if available):
   - Send HTTP POST with query
   - Receive and parse JSON response
   - Calculate total latency

3. **Averaging**:
   - Calculate mean latency across iterations
   - Round to 2 decimal places
   - Store iteration times for variance analysis

### Cache Behavior

**Serena**: File system caching improves performance after warmup. Measured latency reflects steady-state (cached) performance.

**Forgetful**: HTTP connection pooling and model caching improve performance after warmup.

**Implication**: Benchmarks measure typical performance, not worst-case cold start.

## Performance Targets

### Phase 2A Goals

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Serena latency | 530ms | 530ms | Baseline |
| Forgetful latency | Pending | <100ms | Pending M-008 |
| Router overhead | Pending | <50ms | Pending M-008 |
| Total latency (augmented) | Pending | <700ms | Pending M-008 |
| Speedup (Forgetful vs Serena) | Pending | >5x | Goal |

### Long-Term Goals

**Serena Optimization**:

- Implement tiered index (ADR-017) - Target: <200ms
- Add LRU caching for frequently accessed memories - Target: <100ms
- Use memory-mapped files for large memory sets - Target: <150ms

**Forgetful Optimization**:

- Local embedding caching - Target: <50ms
- HNSW index tuning - Target: <30ms
- Connection pooling - Target: <20ms

**Combined Target**: 96-164x vs claude-flow baseline (once baseline is measured)

## Interpreting Results

### Good Performance

```text
Serena Average: 520ms
Forgetful Average: 85ms
Speedup Factor: 6.12x
```

**Indicators**:

- Serena < 600ms (file system performing well)
- Forgetful < 150ms (MCP server responsive)
- Speedup > 3x (semantic search providing value)

### Performance Issues

```text
Serena Average: 1250ms
Forgetful Average: 450ms
Speedup Factor: 2.78x
```

**Possible Causes**:

- Serena: Disk I/O bottleneck, too many memory files, slow filesystem
- Forgetful: Network latency, cold embedding model, database overhead
- Both: CPU throttling, memory pressure, background processes

### Forgetful Unavailable

```text
Serena Average: 530ms
Forgetful: Not available
```

**Expected**: When Forgetful MCP not running. Serena-only performance is baseline.

## Troubleshooting

### High Serena Latency

**Symptoms**: Serena > 800ms consistently

**Diagnosis**:

```powershell
# Check memory file count
(Get-ChildItem ".serena/memories" -Filter "*.md").Count

# Check average file size
Get-ChildItem ".serena/memories" -Filter "*.md" |
    Measure-Object -Property Length -Average |
    Select-Object Average
```

**Solutions**:

1. **Too many files**: Archive old memories, prune obsolete content
2. **Large files**: Split large memories into smaller chunks
3. **Slow disk**: Use SSD, check disk health, reduce I/O contention
4. **Filesystem**: NTFS fragmentation (Windows), ext4 vs btrfs (Linux)

### High Forgetful Latency

**Symptoms**: Forgetful > 500ms consistently

**Diagnosis**:

```bash
# Check Forgetful server logs
journalctl --user -u forgetful -n 50

# Test HTTP endpoint directly
time curl -X POST http://localhost:8020/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"memory_search","arguments":{"query":"test"}}}'
```

**Solutions**:

1. **Cold embedding model**: Run warmup queries before benchmarking
2. **Database overhead**: Check ChromaDB performance, restart if stale
3. **Network latency**: Ensure localhost connectivity, check firewall
4. **Resource contention**: Close other applications, increase memory allocation

### Inconsistent Results

**Symptoms**: High variance in iteration times (>20% standard deviation)

**Solutions**:

1. **Increase iterations**: Use `-Iterations 10` or higher
2. **Increase warmup**: Use `-WarmupIterations 5`
3. **Reduce background load**: Close applications, disable background tasks
4. **Check CPU throttling**: Monitor CPU frequency during benchmarks

### Forgetful Not Detected

**Symptoms**: Benchmark shows "Forgetful: Not available" despite running server

**Diagnosis**:

```powershell
# Test availability manually
Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1
Test-ForgetfulAvailable -Force
```

**Solutions**:

1. **Port mismatch**: Verify Forgetful running on port 8020
2. **Firewall blocking**: Check localhost firewall rules
3. **Server not ready**: Wait for Forgetful startup (check logs)

## Advanced Usage

### Compare Optimizations

```powershell
# Baseline measurement
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1 -Format json > baseline.json

# ... apply optimization ...

# Post-optimization measurement
pwsh scripts/Measure-MemoryPerformance.ps1 -Format json > optimized.json

# Compare results
$baseline = Get-Content baseline.json | ConvertFrom-Json
$optimized = Get-Content optimized.json | ConvertFrom-Json

Write-Host "Serena improvement: $([math]::Round((1 - $optimized.Summary.SerenaAvgMs / $baseline.Summary.SerenaAvgMs) * 100, 2))%"
```

### Analyze Variance

```powershell
# Run with more iterations for statistical analysis
pwsh scripts/Measure-MemoryPerformance.ps1 -Iterations 20 -Format json > results.json

$results = Get-Content results.json | ConvertFrom-Json

foreach ($result in $results.SerenaResults) {
    $times = $result.IterationTimes
    $avg = ($times | Measure-Object -Average).Average
    $stddev = [Math]::Sqrt(($times | ForEach-Object { [Math]::Pow($_ - $avg, 2) } | Measure-Object -Average).Average)
    $cv = $stddev / $avg * 100

    Write-Host "$($result.Query):"
    Write-Host "  Average: $([math]::Round($avg, 2))ms"
    Write-Host "  Std Dev: $([math]::Round($stddev, 2))ms"
    Write-Host "  CV: $([math]::Round($cv, 2))%"
}
```

### Continuous Monitoring

```powershell
# Run benchmarks hourly and track trends
$logFile = "benchmark-history.jsonl"

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    $result = pwsh scripts/Measure-MemoryPerformance.ps1 -Format json | ConvertFrom-Json

    $entry = @{
        timestamp = $timestamp
        serena_avg = $result.Summary.SerenaAvgMs
        forgetful_avg = $result.Summary.ForgetfulAvgMs
    } | ConvertTo-Json -Compress

    Add-Content -Path $logFile -Value $entry
    Start-Sleep -Seconds 3600  # 1 hour
}
```

## Best Practices

### For Development

1. **Run before/after optimizations**: Measure impact of changes
2. **Use consistent hardware**: Don't compare across different machines
3. **Control background load**: Close applications during benchmarking
4. **Check warmup sufficiency**: Ensure caches are hot before measurement

### For CI/CD

1. **Set performance budgets**: Fail build if latency exceeds thresholds
2. **Track trends**: Store benchmark results for historical analysis
3. **Use dedicated hardware**: Avoid shared CI runners for performance tests
4. **Run on schedule**: Daily/weekly benchmarks to catch regressions

### For Documentation

1. **Include hardware specs**: CPU, RAM, disk type in reports
2. **Note environmental factors**: Background load, network conditions
3. **Show variance**: Standard deviation or coefficient of variation
4. **Compare to baseline**: Always reference baseline performance

## Configuration

### Script Configuration

Edit `scripts/Measure-MemoryPerformance.ps1` to customize:

```powershell
# Default queries (line 73-82)
$DefaultQueries = @(
    "your custom query 1"
    "your custom query 2"
)

# Serena memory path (line 91)
$SerenaMemoryPath = ".serena/memories"

# Forgetful endpoint (line 95)
$ForgetfulEndpoint = "http://localhost:8020/mcp"
```

### Environment Variables

Not currently supported. Configuration is hardcoded in script.

**Future Enhancement**: Support `MEMORY_BENCHMARK_QUERIES`, `MEMORY_BENCHMARK_ITERATIONS` env vars.

## Related Documentation

- [Memory Router](memory-router.md) - Understanding what's being benchmarked
- [API Reference](api-reference.md) - Function signatures
- ADR-037 - Memory Router Architecture
- Task M-008 - Memory Search Benchmarks

## References

- **claude-flow baseline**: <https://github.com/ruvnet/claude-flow> (96-164x target)
- **Issue #167**: Vector Memory System
- **PowerShell benchmarking**: `Measure-Command` cmdlet
