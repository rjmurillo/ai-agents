---
name: memory-maintenance
version: 0.1.0
description: Memory-system maintenance operations, split out of the memory router
  per ADR-063. Runs health checks, token-cost counting, atomicity size
  validation, graph-density improvement, and performance benchmarking against the
  canonical memory scripts. Use when you say `check memory health`, `count memory
  tokens`, or `benchmark memory performance`. Do NOT use for Tier 1 search (use
  memory-search) or recording a session (use memory-reflexion).
license: MIT
metadata:
  adr: ADR-007, ADR-037, ADR-063
  type: operation
  parent: memory
---

# Memory Maintenance

Health, budget, atomicity, and performance operations for the memory system,
extracted from the `memory` router per ADR-063 (memory-skill decomposition).
`memory` still routes here; an agent that only needs to check system health or
count a memory's token cost loads this sub-skill instead of the full router.

Maintenance is a family of read-mostly checks over the memory stores. Every
operation delegates to a canonical script under `.claude/skills/memory/scripts/`;
this sub-skill owns the operator guidance, not the script implementations. The
scripts are shared with the router and are not reimplemented here.

## Triggers

Use this skill when the user says:

- `check memory health` for the tier-availability dashboard
- `count memory tokens` for retrieval budget analysis
- `benchmark memory performance` for Serena search latency

## Quick Start

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts"

# System health across all tiers
python3 "$SCRIPTS_DIR/test_memory_health.py" --format table

# Token cost of a memory before you retrieve it
python3 "$SCRIPTS_DIR/count_memory_tokens.py" <memory-file>

# Atomicity size validation (pre-commit gate)
python3 "$SCRIPTS_DIR/test_memory_size.py" <memory-dir> --pattern "*.md"

# Performance benchmark (Serena lexical search, by phase)
python3 "$SCRIPTS_DIR/measure_memory_performance.py" --format table
```

The canonical scripts live at
`.claude/skills/memory/scripts/test_memory_health.py`,
`.claude/skills/memory/scripts/count_memory_tokens.py`, and their siblings. This
sub-skill delegates to them and does not reimplement any check.

## Operations

| Operation | Script | Key Parameters |
|-----------|--------|----------------|
| Health check | `test_memory_health.py` | `--format` (json/table) |
| Token count | `count_memory_tokens.py` | `<memory-file>` |
| Size validation | `test_memory_size.py` | `<memory-dir>`, `--pattern` |
| Benchmark performance | `measure_memory_performance.py` | `--iterations`, `--warmup`, `--format` |
| Improve graph density | `improve_memory_graph_density.py` | `--memory-path`, `--dry-run` |
| Cross-reference | `invoke_memory_cross_reference.py` | `--memory-path`, `--threshold` |
| Convert index links | `convert_index_table_links.py` | `--memory-path`, `--dry-run` |

## Health Check

```bash
python3 "$SCRIPTS_DIR/test_memory_health.py" --format table
```

A healthy system reports `available: true` for each tier. Every tier is now
backed by files in the working tree, so `available: false` means a missing or
unreadable directory rather than a service being down, and there is no
fallback mode to select. Use the health check before a maintenance batch so you
know which tiers are readable.

## Token Cost Visibility

```bash
python3 "$SCRIPTS_DIR/count_memory_tokens.py" <memory-file>
# Output: memory-index.md: 2,450 tokens
```

Count tokens before retrieval so the return-on-investment decision is informed.
A SHA-256 hash-based cache gives a 10x to 100x speedup on repeated queries. See
[scripts/README-count-tokens.md](../memory/scripts/README-count-tokens.md) for
the cache layout and flags.

## Size Validation

```bash
python3 "$SCRIPTS_DIR/test_memory_size.py" <memory-dir> --pattern "*.md"
# Exit 0 (pass) or 1 (fail) with decomposition recommendations
```

Atomic memories keep the token cost low: one retrievable concept per file.
Thresholds (from the `memory-size-001-decomposition-thresholds` memory):

- Max 10,000 chars (about 2,500 tokens, atomic memory)
- Max 15 skills (independent concepts per file)
- Max 5 categories (domain focus)

See [scripts/README-test-size.md](../memory/scripts/README-test-size.md) for the
full threshold rationale.

## Graph Density and Cross-Reference

```bash
# Suggest cross-links to raise knowledge-graph density
python3 "$SCRIPTS_DIR/improve_memory_graph_density.py" --dry-run

# Compute reference candidates above a similarity threshold
python3 "$SCRIPTS_DIR/invoke_memory_cross_reference.py" --threshold 0.7
```

Density work is advisory: run it with `--dry-run` first, review the proposed
links, then apply. Denser cross-linking improves multi-hop retrieval; over-dense
linking adds noise. Prefer a threshold that adds few, high-confidence links.

## Performance Benchmarking

```bash
python3 "$SCRIPTS_DIR/measure_memory_performance.py" --format table
```

The benchmark measures Serena lexical search latency, split into its listing,
matching, and reading phases. Use it to confirm a change did not regress
retrieval speed. The full method and the query set are in
[references/benchmarking.md](references/benchmarking.md).

## Verification

| Operation | Verification |
|-----------|--------------|
| Health check | All tiers show `available: true` (or a known degraded tier) |
| Token count | CLI prints the file name and a token total |
| Size validation | Exit 0 (pass) or 1 with a decomposition recommendation |
| Benchmark | Latency report prints for each backend queried |
| Density dry run | Proposed links print and nothing is written |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Retrieving a memory blind | Count tokens first; decide on the return on investment |
| Letting memories grow large | Run size validation; decompose past the thresholds |
| Applying density links blind | Dry-run first; apply only high-confidence links |
| Skipping the health check | Confirm tier availability before a maintenance batch |
| Trusting a slow retrieval | Benchmark; confirm the change did not regress latency |

## Process

### Phase 1: Assess

Run the health check to learn which tiers are reachable and whether any store is
degraded.

### Phase 2: Measure

Run the specific maintenance operation (token count, size validation, benchmark,
or density) against the target memories.

### Phase 3: Act

Apply size decomposition or density links only after a dry run confirms the
change. Re-run the relevant check to verify the result.

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory` | Router for search, reflexion, or gate operations |
| `memory-search` | Tier 1 semantic lookup, not a maintenance check |
| `memory-reflexion` | Record a completed session as an episode |
| `curating-memories` | Content maintenance (obsolete, deduplicate, link) |

## Troubleshooting

| Symptom | Cause | Recovery |
|---------|-------|----------|
| Health check shows a tier down | Store directory missing or unreadable | Verify the path exists; every tier is local files, so this is not a service outage |
| Token count slow | Cache cold on first run | Re-run; the SHA-256 cache warms after the first pass |
| Size validation fails | Memory past atomicity thresholds | Decompose the memory into atomic files per the recommendation |
| Benchmark latency high | Large corpus, or many files matched and read | Read the per-phase split: listing, matching, and reading are timed separately |

See [references/troubleshooting.md](references/troubleshooting.md) for the full
diagnostic tables by component and symptom, and
[references/benchmarking.md](references/benchmarking.md) for the performance
targets.

## References

- ADR-007: Memory-first architecture (canonical store, local-only posture)
- ADR-037: Memory router architecture (the router this sub-skill delegates from)
- ADR-063: Memory skill decomposition (this extraction)
- [references/benchmarking.md](references/benchmarking.md): benchmark method,
  query set, and target ratios
- [references/troubleshooting.md](references/troubleshooting.md): diagnostics by
  component and symptom
