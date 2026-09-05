# Memory Router
<!-- # taste-lint: ignore file-size -->
<!-- file-size rationale: reference doc for the memory API; every entry
documents a real entry point verified by test_reference_docs_resolve.py,
and splitting the reference breaks lookup by single file. -->

## Overview

The Memory Router searches every memory tier from one call. Two artifacts make
it up:

| Artifact | Role |
|----------|------|
| `.claude/skills/memory/memory_core/memory_router.py` | Importable module. Serena only. |
| `.claude/skills/memory/scripts/search_memory.py` | CLI wrapper. Adds the Tier 2 episode store. |

Agents call the CLI. Python callers import the module.

**ADR**: ADR-037 Memory Router Architecture

**Task**: M-003 (Phase 2A Memory System)

## Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                          Memory Router                               │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ search_memory.py "pattern" --max-results 10                    │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                │                                     │
│                ┌───────────────┴───────────────┐                     │
│                ▼                               ▼                     │
│         ┌──────────────┐              ┌──────────────────┐           │
│         │ Serena       │              │ Episodes         │           │
│         │ (Canonical)  │              │ (Tier 2)         │           │
│         │ .serena/     │              │ .agents/memory/  │           │
│         │   memories   │              │   episodes       │           │
│         │              │              │                  │           │
│         │ Always avail │              │ Always avail     │           │
│         │ Git-synced   │              │ Git-synced       │           │
│         │ Lexical      │              │ Lexical, recency │           │
│         └──────────────┘              └──────────────────┘           │
│            (module)                        (CLI only)                │
└──────────────────────────────────────────────────────────────────────┘
```

## Core Concepts

### One Store, No Routing

Serena is the only backend. It travels with the Git repository as plain
markdown under `.serena/memories/`, so a search reads the working tree and
cannot fail the way a network service can.

The second, semantic backend this router augmented with was decommissioned in
issue #5574. Nothing replaced it. What went with it: the availability probe
and its 30-second cache, the SHA-256 cross-source result merge, and the two
parameters that selected between the stores.

## Usage

### Command Line (Agent-Facing)

The query is a **positional** argument. There is no `--query` flag.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "git hooks" --format json
```

Full option set:

| Option | Default | Description |
|--------|---------|-------------|
| `query` (positional) | required | Search query, 1-500 chars |
| `--max-results N` | 10 | Maximum results (1-100) |
| `--format {json,table}` | `json` | Output format |
| `--serena-path PATH` | `.serena/memories` | Override the Serena store |
| `--episodes-path PATH` | `.agents/memory/episodes` | Override the episode store |

The CLI is the only path that searches the Tier 2 episode store. Results from
that tier carry `source: "Episodes"`.

### Python Import

`memory_core` is a package under the skill, not an installed distribution. Add
the skill directory to `sys.path` first. The `skills/memory/tests/conftest.py`
file in this tree does exactly this.

```python
import os
import sys
_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".claude"
sys.path.insert(0, f"{_root}/skills/memory")

from memory_core.memory_router import search_memory

results = search_memory("git hooks", max_results=10)
for result in results:
    print(f"{result.name} (source={result.source}, score={result.score})")
    print(result.content)
```

## Functions

### search_memory

Main entry point for unified memory search.

**Signature**:

```python
def search_memory(
    query: str,
    max_results: int = 10,
) -> list[MemoryResult]: ...
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | required | Search query (1-500 chars, alphanumeric plus safe punctuation) |
| `max_results` | `int` | 10 | Maximum results to return (1-100) |

**Returns**: `list[MemoryResult]`. `MemoryResult` is a dataclass with:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Memory name |
| `content` | `str \| None` | Full memory content. Always populated by `search_memory`. |
| `source` | `str` | `"Serena"` |
| `score` | `float` | Percent of query keywords matched. |
| `path` | `str \| None` | File path |
| `hash` | `str \| None` | SHA-256 content hash. Always populated by `search_memory`. |
| `id` | `str \| None` | Always `None`. The retired backend supplied it. |

**Raises**:

| Exception | Condition |
|-----------|-----------|
| `ValueError` | Query empty, over 500 chars, or outside the allowed character class |
| `ValueError` | `max_results` outside 1-100 |
| `TypeError` | Either removed backend-selection parameter was passed |

**Measured example**:

```python
>>> search_memory("git hooks", max_results=3)
[MemoryResult(name='skills-git-hooks-index', content='# Git hooks...',
              source='Serena', score=100.0,
              path='.serena/memories/skills-git-hooks-index.md',
              hash='9f2b...', id=None),
 MemoryResult(name='copilot-disable-all-hooks-windows', ..., score=50.0, ...),
 MemoryResult(name='copilot-hooks-observations', ..., score=50.0, ...)]
```

### get_memory_router_status

Returns diagnostic information about the router.

**Signature**:

```python
def get_memory_router_status() -> dict[str, Any]: ...
```

Top-level keys are capitalized; the keys inside `Configuration` are snake_case
because they mirror the module `_config` dict verbatim.

**Measured output**:

```json
{
 "Serena":        {"Available": true,  "Path": ".serena/memories"},
 "Configuration": {
   "serena_path": ".serena/memories",
   "max_results": 10
 }
}
```

### reset_caches

Clears the file-list cache. Test-only.

```python
def reset_caches() -> None: ...
```

## Internal Functions (Private)

### invoke_serena_search

Performs lexical search across Serena memory files.

**Scoring**: percent of query keywords matching in the filename.

**Steps**:

1. Extract keywords from query (length > 2 chars)
2. List all `.md` files in `.serena/memories/` (10s cached listing)
3. Match keywords against file basenames
4. Score as `(matching_keywords / total_keywords) * 100`
5. Read content for matched files, unless `skip_content` is set
6. Sort by score descending

### get_content_hash

SHA-256 over UTF-8 bytes, lowercase hex output. Used for deduplication.

## Configuration

Configuration lives in a module-level dict:

```python
_config: dict[str, Any] = {
    "serena_path": ".serena/memories",
    "max_results": 10,
}
```

The leading underscore marks it private; prefer the CLI `--serena-path` and
`--episodes-path` flags over mutating it.

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Serena search | ~530ms | O(n) file scan plus keyword match |
| File-list cache read | <1ms | Dataclass field read, 10s TTL |
| **Total** | ~530ms | No network on any path |

Every path is local file I/O now, so latency is a function of corpus size
rather than of a service being up.

Measure with `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py"`.

## Security

### Input Validation

`search_memory` validates before any I/O:

```python
if not query or len(query) > 500:
    raise ValueError("Query must be 1-500 characters")
if not re.match(r"^[a-zA-Z0-9\s\-.,_()&:]+$", query):
    raise ValueError("Query contains invalid characters")
if max_results < 1 or max_results > 100:
    raise ValueError("max_results must be between 1 and 100")
```

**Prevents**:

- Regex injection (CWE-20)
- Path traversal (CWE-22)
- Command injection (CWE-78)

### Transport Security

| Connection | Protocol | Security |
|------------|----------|----------|
| Serena | Local file I/O | No network exposure |
| Episodes | Local file I/O | No network exposure |

The router makes no outbound request of any kind. Reintroducing one means
reintroducing URL-scheme validation with it, which
`tests/skills/memory/test_url_validation.py` asserts against.

### Data Handling

- **No secrets in queries**: queries must not contain credentials, API keys, or PII
- **Content hashing**: SHA-256 for deduplication
- **Logging**: query patterns are logged at DEBUG; content is not logged

## Error Handling

### Invalid Query

```python
search_memory("test; rm -rf /")
# ValueError: Query contains invalid characters
```

### Removed Parameters

```python
search_memory("test", lexical_only=True)
# TypeError: search_memory() got an unexpected keyword argument 'lexical_only'
```

## Troubleshooting

### No Serena Results

**Symptoms**: `search_memory` returns an empty list while memories exist.

**Diagnosis**:

```bash
ls .serena/memories/*.md | head
```

**Solutions**:

1. Verify `.serena/memories/` exists
2. Serena scores on the **filename**, so keywords must appear in the file name
3. Try a broader query with common terms

### Slow Searches

**Symptoms**: searches consistently take over one second.

**Diagnosis**:

```bash
time uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "test"
```

**Solutions**:

1. Lower `--max-results` to reduce file reads
2. Narrow the query; every matched file is read in full for its preview
3. Check the corpus size: search is O(n) over `.serena/memories/*.md`

## Best Practices

### For Agents

1. **Use the CLI**: do not call the Serena MCP directly
2. **Bound results**: pass `--max-results` for what you actually need
3. **Handle empty results**: the return is a list; check it before indexing

### For Skill Authors

1. **Call the script**: `.claude/skills/memory/scripts/search_memory.py`
2. **Parse JSON**: `--format json` gives structured output
3. **Include diagnostics**: pair results with `get_memory_router_status()`

### For Developers

1. **Point at a fixture corpus**: patch `_config["serena_path"]` at a tmp dir
2. **Reset caches**: call `reset_caches()` between tests that write memory files
3. **Profile**: `measure_memory_performance.py`

## Related Documentation

- [Reflexion Memory](../../memory-reflexion/references/reflexion-memory.md) - Episodic memory (Tier 2)
- [Benchmarking](../../memory-maintenance/references/benchmarking.md) - Performance measurement
- [API Reference](api-reference.md) - Complete function signatures
- ADR-037 - Memory Router Architecture
- ADR-007 - Memory-First Architecture

<!-- vendor-portability: declared. The CLI defaults table names `.agents/memory/episodes` as the episode store's default location. That path is the consumer's own data dir, created on demand when absent, and `--episodes-path` overrides it. A vendored install without the dir loses the Tier 2 episode results, not the search. Issue #2050. -->
