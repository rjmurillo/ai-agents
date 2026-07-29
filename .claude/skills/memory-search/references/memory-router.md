# Memory Router

## Overview

The Memory Router searches every memory tier from one call. Two artifacts make
it up:

| Artifact | Role |
|----------|------|
| `.claude/skills/memory/memory_core/memory_router.py` | Importable module. Serena plus Forgetful. |
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
│      ┌─────────────────────────┼─────────────────────────┐           │
│      ▼                         ▼                         ▼           │
│ ┌──────────────┐      ┌──────────────────┐      ┌──────────────────┐ │
│ │ Serena       │      │ Episodes         │      │ Forgetful        │ │
│ │ (Canonical)  │      │ (Tier 2)         │      │ (Augmentation)   │ │
│ │ .serena/     │      │ .agents/memory/  │      │ Port 8020        │ │
│ │   memories   │      │   episodes       │      │                  │ │
│ │              │      │                  │      │                  │ │
│ │ Always avail │      │ Always avail     │      │ Semantic         │ │
│ │ Git-synced   │      │ Git-synced       │      │ Embeddings       │ │
│ │ Lexical      │      │ Lexical, recency │      │ Local-only       │ │
│ └──────────────┘      └──────────────────┘      └──────────────────┘ │
│      (module)              (CLI only)                 (module)       │
└──────────────────────────────────────────────────────────────────────┘
```

## Core Concepts

### Serena-First Routing

The router always queries Serena first (canonical source), then optionally
augments with Forgetful semantic results.

**Rationale**: Serena travels with the Git repository, ensuring cross-platform
availability. Forgetful provides enhanced semantic search but requires a
running service.

### Result Augmentation

Forgetful results enhance but never replace Serena results.

**Merge Strategy**:

1. Query Serena (always)
2. Query Forgetful (if available and `lexical_only` is not set)
3. Deduplicate by SHA-256 content hash
4. Return Serena results plus unique Forgetful matches

### Availability Detection

The router detects Forgetful availability with a cached TCP health check
(30s TTL, 0.5s connect timeout).

**Failure Mode**: degrades to Serena-only if Forgetful is unavailable. No error
is raised unless the caller asked for `semantic_only`.

## Usage

### Command Line (Agent-Facing)

The query is a **positional** argument. There is no `--query` flag.

```bash
uv run python .claude/skills/memory/scripts/search_memory.py "git hooks" --format json
```

Full option set:

| Option | Default | Description |
|--------|---------|-------------|
| `query` (positional) | required | Search query, 1-500 chars |
| `--max-results N` | 10 | Maximum results (1-100) |
| `--lexical-only` | off | File-based stores only (Serena and episodes) |
| `--semantic-only` | off | Forgetful only |
| `--format {json,table}` | `json` | Output format |
| `--serena-path PATH` | `.serena/memories` | Override the Serena store |
| `--episodes-path PATH` | `.agents/memory/episodes` | Override the episode store |

The CLI is the only path that searches the Tier 2 episode store. Results from
that tier carry `source: "Episodes"`.

### Python Import

`memory_core` is a package under the skill, not an installed distribution. Add
the skill directory to `sys.path` first. `.claude/skills/memory/tests/conftest.py`
does exactly this.

```python
import sys
sys.path.insert(0, ".claude/skills/memory")

from memory_core.memory_router import search_memory

results = search_memory("git hooks", max_results=10)
for result in results:
    print(f"{result.name} (source={result.source}, score={result.score})")
    print(result.content)
```

### Lexical-Only Search

Skips Forgetful entirely:

```python
results = search_memory("git hooks", lexical_only=True)
```

**Use When**: performance is critical, or Forgetful is known to be unavailable.

**Caveat**: lexical-only skips reading file content, so every result comes back
with `content=None` and `hash=None`. Only `name`, `source`, `score`, and `path`
are populated. Ask for the augmented mode if you need the body.

### Semantic-Only Search

Requires Forgetful to be running:

```python
try:
    results = search_memory("authentication patterns", semantic_only=True)
except RuntimeError as exc:
    print(f"Forgetful unavailable: {exc}")
```

**Use When**: you need semantic similarity specifically, not keyword matching.

## Functions

### search_memory

Main entry point for unified memory search.

**Signature**:

```python
def search_memory(
    query: str,
    max_results: int = 10,
    semantic_only: bool = False,
    lexical_only: bool = False,
) -> list[MemoryResult]: ...
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | required | Search query (1-500 chars, alphanumeric plus safe punctuation) |
| `max_results` | `int` | 10 | Maximum results to return (1-100) |
| `semantic_only` | `bool` | `False` | Force Forgetful-only search (raises if unavailable) |
| `lexical_only` | `bool` | `False` | Force Serena-only search (always available) |

**Returns**: `list[MemoryResult]`. `MemoryResult` is a dataclass with:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Memory name |
| `content` | `str \| None` | Full memory content. `None` under `lexical_only`. |
| `source` | `str` | `"Serena"` or `"Forgetful"` |
| `score` | `float` | Serena: percent of query keywords matched. Forgetful: similarity. |
| `path` | `str \| None` | File path (Serena only) |
| `hash` | `str \| None` | SHA-256 content hash. `None` under `lexical_only`. |
| `id` | `str \| None` | Forgetful record id |

**Raises**:

| Exception | Condition |
|-----------|-----------|
| `ValueError` | Both `semantic_only` and `lexical_only` set |
| `ValueError` | Query empty, over 500 chars, or outside the allowed character class |
| `ValueError` | `max_results` outside 1-100 |
| `RuntimeError` | `semantic_only` set and Forgetful is unavailable |

**Measured example**:

```python
>>> search_memory("git hooks", max_results=3, lexical_only=True)
[MemoryResult(name='skills-git-hooks-index', content=None, source='Serena',
              score=100.0, path='.serena/memories/skills-git-hooks-index.md',
              hash=None, id=None),
 MemoryResult(name='copilot-disable-all-hooks-windows', ..., score=50.0, ...),
 MemoryResult(name='copilot-hooks-observations', ..., score=50.0, ...)]
```

### test_forgetful_available

Checks whether Forgetful MCP is reachable, with 30s caching.

**Signature**:

```python
def test_forgetful_available(port: int = 8020, force: bool = False) -> bool: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | `int` | 8020 | Forgetful server port |
| `force` | `bool` | `False` | Skip the cache and re-check |

**Returns**: `bool`.

The name begins with `test_` for historical reasons. The module sets
`__test__ = False` on it so pytest does not collect the production function as
a test case. Do not rename it without updating every caller.

```python
if test_forgetful_available():
    print("Forgetful is available")
else:
    print("Forgetful is unavailable, using Serena-only")
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
 "Forgetful":     {"Available": false, "Endpoint": "http://localhost:8020/mcp"},
 "Cache":         {"AgeSeconds": 0.0, "TTLSeconds": 30.0},
 "Configuration": {
   "serena_path": ".serena/memories",
   "forgetful_port": 8020,
   "forgetful_timeout": 0.5,
   "max_results": 10
 }
}
```

### reset_caches

Clears the health-check and file-list caches. Test-only.

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

### invoke_forgetful_search

Performs semantic search via the Forgetful MCP HTTP endpoint.

**Protocol**: JSON-RPC 2.0 over HTTP, 10s read timeout.

**Steps**:

1. Build a JSON-RPC request for the `memory_search` tool
2. POST to `http://localhost:8020/mcp`
3. Parse the MCP tool response
4. Extract memories from the response content
5. Return structured results

### merge_memory_results

Merges and deduplicates results from Serena and Forgetful.

**Algorithm**:

1. Build a hash set from Serena results (SHA-256 of content)
2. Add all Serena results to the merged set
3. For each Forgetful result, hash the content; add it only if the hash is new
4. Truncate to `max_results`

**Serena Priority**: Serena results appear first and win on content collision.

### get_content_hash

SHA-256 over UTF-8 bytes, lowercase hex output. Used for deduplication.

## Configuration

Configuration lives in a module-level dict:

```python
_config: dict[str, Any] = {
    "serena_path": ".serena/memories",
    "forgetful_port": 8020,
    "forgetful_timeout": 0.5,  # seconds
    "max_results": 10,
}
```

`forgetful_timeout` is in **seconds**, and it is passed straight to
`socket.settimeout`. The leading underscore marks it private; prefer the CLI
`--serena-path` and `--episodes-path` flags over mutating it.

## Health Check Details

### Caches

| Cache | TTL | Contents |
|-------|-----|----------|
| Health | 30s | Forgetful reachability |
| File list | 10s | The `.serena/memories/*.md` listing |

**Rationale**: both balance freshness against latency. Availability and the
memory file set are stable within a session.

### TCP Check

**Method**: `connect_ex` to `localhost:8020`.

**Timeout**: 0.5s.

**Rationale**: fast enough for a per-session check. A slow service fails early
instead of blocking queries.

### Failure Handling

**On Failure**: cache `available = False` for 30s and return `False`.

**No Retry**: a failed health check is not retried until the cache expires. Pass
`force=True` to bypass.

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Serena search | ~530ms | O(n) file scan plus keyword match |
| Forgetful search | Variable | Network, embedding, vector search |
| Health check (cached) | <1ms | Dataclass field read |
| Health check (fresh) | 1-500ms | TCP connect with timeout |
| Result merge | <10ms | Hash-based deduplication |
| **Total (Serena-only)** | ~530ms | Baseline, no network |
| **Total (augmented)** | ~700ms | Serena plus Forgetful plus merge |

**Target**: router overhead under 50ms when Forgetful is available.

Measure with `uv run python .claude/skills/memory/scripts/measure_memory_performance.py`.

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
| Forgetful | HTTP localhost:8020 | Localhost-only (no TLS) |

**Assumption**: Forgetful runs on localhost only. Remote deployment would
require HTTPS.

### Data Handling

- **No secrets in queries**: queries must not contain credentials, API keys, or PII
- **Content hashing**: SHA-256 for deduplication
- **Logging**: query patterns are logged at DEBUG; content is not logged

## Error Handling

### Forgetful Unavailable

```python
results = search_memory("test")
# Serena results only. No error.
```

### Forgetful Required but Unavailable

```python
search_memory("test", semantic_only=True)
# RuntimeError: Forgetful is not available and semantic_only was specified
```

### Invalid Query

```python
search_memory("test; rm -rf /")
# ValueError: Query contains invalid characters
```

### Mutually Exclusive Flags

```python
search_memory("test", semantic_only=True, lexical_only=True)
# ValueError: Cannot specify both semantic_only and lexical_only
```

## Troubleshooting

### Forgetful Not Detected

**Symptoms**: `test_forgetful_available()` returns `False` while Forgetful is running.

**Diagnosis**:

```python
test_forgetful_available(force=True)  # skip the 30s cache
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8020/mcp
```

**Solutions**:

1. Verify Forgetful is running: `systemctl --user status forgetful`
2. Check the port: `ss -ltn 'sport = :8020'`
3. Review logs: `journalctl --user -u forgetful -n 50`

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
time uv run python .claude/skills/memory/scripts/search_memory.py "test" --lexical-only
time uv run python .claude/skills/memory/scripts/search_memory.py "test"
```

**Solutions**:

1. Pass `--lexical-only` when semantic search is not needed
2. Lower `--max-results` to reduce file reads
3. Check the Forgetful response time; the first query is often slow

## Best Practices

### For Agents

1. **Use the CLI**: do not call Serena or Forgetful MCP directly
2. **Bound results**: pass `--max-results` for what you actually need
3. **Check availability**: call `test_forgetful_available()` if semantic search is critical
4. **Handle empty results**: the return is a list; check it before indexing

### For Skill Authors

1. **Call the script**: `.claude/skills/memory/scripts/search_memory.py`
2. **Parse JSON**: `--format json` gives structured output
3. **Include diagnostics**: pair results with `get_memory_router_status()`

### For Developers

1. **Test both modes**: verify Serena-only and augmented paths
2. **Avoid the network in tests**: pass `lexical_only=True`
3. **Reset caches**: call `reset_caches()` between tests that fake availability
4. **Profile**: `measure_memory_performance.py`

## Related Documentation

- [Reflexion Memory](../../memory-reflexion/references/reflexion-memory.md) - Episodic memory (Tier 2)
- [Benchmarking](../../memory-maintenance/references/benchmarking.md) - Performance measurement
- [API Reference](api-reference.md) - Complete function signatures
- ADR-037 - Memory Router Architecture
- ADR-007 - Memory-First Architecture
