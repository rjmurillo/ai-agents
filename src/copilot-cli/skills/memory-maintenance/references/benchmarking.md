# Memory System Benchmarking

## Overview

Memory search performance benchmarking tool for measuring Serena lexical search latency, split into its listing, matching, and reading phases.

**Script**: `skills/memory/scripts/measure_memory_performance.py`, relative to the plugin root

**Task**: M-008 (Phase 2A Memory System)

**Target**: 96-164x performance vs claude-flow baseline for equivalent operations

## Quick Start

```bash
# Run default benchmarks (8 queries, 5 iterations each)
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py"

# Custom queries with more iterations
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" \
    --queries "PowerShell arrays" "git hooks" \
    --iterations 10

# Markdown report for documentation
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" > benchmark-report.md

# JSON output for programmatic analysis
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" --format json
```

## Usage

### Basic Benchmarking

```bash
# No import required - script is self-contained
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py"

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
```

### Custom Queries

```bash
# Define domain-specific queries
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" \
    --queries \
        "PowerShell module patterns" \
        "Git pre-commit validation" \
        "Agent coordination protocols" \
        "Memory-first architecture" \
    --iterations 10
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

| System | Average (ms) |
|--------|-------------|
| Serena | 530.12 |
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
    "SerenaPath": ".serena/memories"
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
  "Summary": {
    "SerenaAvgMs": 530.12
  }
}
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| --queries | str[] | Default set | List of test queries to benchmark |
| --iterations | int | 5 | Number of iterations per query for averaging |
| --warmup-iterations | int | 2 | Number of warmup iterations before measurement |
| --format | str | console | Output format: console, markdown, json |

### Default Query Set

The script includes 8 default queries covering different domains:

```python
[
    "PowerShell array handling patterns",
    "git pre-commit hook validation",
    "GitHub CLI PR operations",
    "session protocol compliance",
    "security vulnerability detection",
    "Pester test isolation",
    "CI workflow patterns",
    "memory-first architecture",
]
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

### Summary Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| SerenaAvgMs | Average Serena search latency | 530ms (baseline) |

The summary carried two more metrics, a second backend's average and the ratio
between the two, until issue #5574 retired that backend. A ratio needs two
operands, so both were removed rather than reported as zero.

## Measurement Methodology

### Warmup Phase

Warmup iterations run before measurement to:

- Populate file system caches
- Reach steady-state directory listing cost
- Stabilize CPU frequency scaling

**Default**: 2 warmup iterations (not measured)

### Measurement Phase

Each query is executed multiple times (default: 5 iterations):

1. **Serena**:
   - List all memory files
   - Match keywords against filenames
   - Read matched file contents
   - Calculate total latency

2. **Averaging**:
   - Calculate mean latency across iterations
   - Round to 2 decimal places
   - Store iteration times for variance analysis

### Cache Behavior

**Serena**: File system caching improves performance after warmup. Measured latency reflects steady-state (cached) performance.

**Implication**: Benchmarks measure typical performance, not worst-case cold start.

## Performance Targets

### Phase 2A Goals

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Serena latency | 530ms | 530ms | Baseline |

### Long-Term Goals

**Serena Optimization**:

- Implement tiered index (ADR-017) - Target: <200ms
- Add LRU caching for frequently accessed memories - Target: <100ms
- Use memory-mapped files for large memory sets - Target: <150ms

The claude-flow comparison target that sat here was a ratio against a second
backend. It is gone with that backend (issue #5574); the remaining target is
the absolute Serena latency above.

## Interpreting Results

### Good Performance

```text
Serena Average: 520ms
```

**Indicators**:

- Serena < 600ms (file system performing well)
- ReadTimeMs dominating TotalTimeMs is expected: reading matched files is the
  bulk of the work

### Performance Issues

```text
Serena Average: 1250ms
```

**Possible Causes**:

- Disk I/O bottleneck, too many memory files, slow filesystem
- A broad query matching many files, so ReadTimeMs dominates
- CPU throttling, memory pressure, background processes

## Troubleshooting

### High Serena Latency

**Symptoms**: Serena > 800ms consistently

**Diagnosis**:

```bash
# Check memory file count
find .serena/memories -name "*.md" | wc -l

# Check average file size
find .serena/memories -name "*.md" -exec wc -c {} + | awk '{total += $1; count++} END {print total/count " bytes avg"}'
```

**Solutions**:

1. **Too many files**: Archive old memories, prune obsolete content
2. **Large files**: Split large memories into smaller chunks
3. **Slow disk**: Use SSD, check disk health, reduce I/O contention
4. **Filesystem**: NTFS fragmentation (Windows), ext4 vs btrfs (Linux)

### Inconsistent Results

**Symptoms**: High variance in iteration times (>20% standard deviation)

**Solutions**:

1. **Increase iterations**: Use `--iterations 10` or higher
2. **Increase warmup**: Use `--warmup-iterations 5`
3. **Reduce background load**: Close applications, disable background tasks
4. **Check CPU throttling**: Monitor CPU frequency during benchmarks

## Advanced Usage

### Compare Optimizations

```bash
# Baseline measurement
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" --format json > baseline.json

# ... apply optimization ...

# Post-optimization measurement
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" --format json > optimized.json

# Compare results
python3 -c "
import json
baseline = json.load(open('baseline.json'))
optimized = json.load(open('optimized.json'))
improvement = round((1 - optimized['Summary']['SerenaAvgMs'] / baseline['Summary']['SerenaAvgMs']) * 100, 2)
print(f'Serena improvement: {improvement}%')
"
```

### Analyze Variance

```bash
# Run with more iterations for statistical analysis
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" --iterations 20 --format json > results.json

python3 -c "
import json, math
results = json.load(open('results.json'))
for result in results['SerenaResults']:
    times = result['IterationTimes']
    avg = sum(times) / len(times)
    stddev = math.sqrt(sum((t - avg) ** 2 for t in times) / len(times))
    cv = stddev / avg * 100
    print(f'{result[\"Query\"]}:')
    print(f'  Average: {avg:.2f}ms')
    print(f'  Std Dev: {stddev:.2f}ms')
    print(f'  CV: {cv:.2f}%')
"
```

### Continuous Monitoring

```bash
# Run benchmarks hourly and track trends
LOG_FILE="benchmark-history.jsonl"

while true; do
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S")
    RESULT=$(python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" --format json)

    echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
entry = {
    'timestamp': '$TIMESTAMP',
    'serena_avg': data['Summary']['SerenaAvgMs'],
}
print(json.dumps(entry))
" >> "$LOG_FILE"

    sleep 3600  # 1 hour
done
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

Edit `skills/memory/scripts/measure_memory_performance.py`, relative to the plugin root, to customize:

```python
# Default queries
DEFAULT_QUERIES = [
    "your custom query 1",
    "your custom query 2",
]

# Serena memory path
SERENA_MEMORY_PATH = ".serena/memories"
```

### Environment Variables

Not currently supported. Configuration is hardcoded in script.

**Future Enhancement**: Support `MEMORY_BENCHMARK_QUERIES`, `MEMORY_BENCHMARK_ITERATIONS` env vars.

## Related Documentation

- [Memory Router](../../memory-search/references/memory-router.md) - Understanding what's being benchmarked
- [API Reference](../../memory-search/references/api-reference.md) - Function signatures
- ADR-037 - Memory Router Architecture
- Task M-008 - Memory Search Benchmarks

## References

- **claude-flow baseline**: <https://github.com/ruvnet/claude-flow> (96-164x target)
- **Issue #167**: Vector Memory System
- **Python benchmarking**: `time` module (`time.perf_counter()`)
