# Memory System API Reference

Complete reference for the public functions in the memory system.

Every function below is Python. The repository ships no PowerShell: `git ls-files '*.ps1' '*.psm1'` returns zero files, and ADR-042 makes Python the only scripting language for new work.

## Importing

`memory_core` is a package under the memory skill, not an installed distribution. Put the skill root on `sys.path` first:

```python
import sys
sys.path.insert(0, ".claude/skills/memory")

from memory_core.memory_router import search_memory
from memory_core.reflexion_memory import get_episode
```

`.claude/skills/memory/tests/conftest.py` does exactly this for the test suite.

## Module Index

| Module | Purpose | Location |
|--------|---------|----------|
| [memory_router](#memory_router-module) | Unified memory search (Tier 1) | `.claude/skills/memory/memory_core/memory_router.py` |
| [reflexion_memory](#reflexion_memory-module) | Session episodes (Tier 2) | `.claude/skills/memory/memory_core/reflexion_memory.py` |

Two scripts wrap these modules with a command line: `.claude/skills/memory/scripts/search_memory.py` and `.claude/skills/memory/scripts/extract_session_episode.py`.

## memory_router Module

### search_memory

Unified memory search across Serena and Forgetful.

**Signature**:

```python
def search_memory(
    query: str,
    max_results: int = 10,
    semantic_only: bool = False,
    lexical_only: bool = False,
) -> list[MemoryResult]
```

**Parameters**:

- **query** (`str`, required): Search query, 1-500 chars. Pattern: `^[a-zA-Z0-9\s\-.,_()&:]+$`
- **max_results** (`int`): Maximum results to return, 1-100. Default 10.
- **semantic_only** (`bool`): Force Forgetful-only search. Raises if Forgetful is unavailable.
- **lexical_only** (`bool`): Force Serena-only search. Always available.

**Returns**: `list[MemoryResult]`. See [MemoryResult](#memoryresult).

**Raises**:

- `ValueError`: both `semantic_only` and `lexical_only` were passed, or the query failed validation.
- `RuntimeError`: `semantic_only` was passed and Forgetful is unavailable.

**Example**:

```python
for r in search_memory("python arrays", max_results=5):
    print(f"{r.name} (source: {r.source}, score: {r.score})")
```

**Command line**:

```bash
uv run python .claude/skills/memory/scripts/search_memory.py "python arrays" --max-results 5
```

---

### MemoryResult

The dataclass every search function returns.

| Field | Type | Meaning |
|-------|------|---------|
| `name` | `str` | Memory name |
| `content` | `str \| None` | Full memory content. `None` when `skip_content` was set. |
| `source` | `str` | `"Serena"` or `"Forgetful"` |
| `score` | `float` | Relevance. Serena: fraction of query keywords matched. Forgetful: similarity. |
| `path` | `str \| None` | File path. Serena only. |
| `hash` | `str \| None` | SHA-256 content hash, 64 lowercase hex chars. |
| `id` | `int \| None` | Forgetful record id. `None` for Serena results. |

---

### invoke_serena_search

Lexical search across Serena memory files.

**Signature**:

```python
def invoke_serena_search(
    query: str,
    memory_path: str = ".serena/memories",
    max_results: int = 10,
    skip_content: bool = False,
) -> list[MemoryResult]
```

Scoring is the fraction of query keywords that appear in the filename. `skip_content=True` skips file reads and SHA-256 hashing, which is the fast path when only names are needed.

---

### invoke_forgetful_search

Semantic search via the Forgetful MCP HTTP endpoint, using JSON-RPC 2.0.

**Signature**:

```python
def invoke_forgetful_search(
    query: str,
    endpoint: str = "http://localhost:8020/mcp",
    max_results: int = 10,
) -> list[MemoryResult]
```

`endpoint` must use the `http` or `https` scheme. Other schemes (`file://`, `ftp://`) are rejected.

---

### merge_memory_results

Merges and deduplicates results from both sources using SHA-256 content hashing. Serena results take priority: they appear first and are treated as canonical.

**Signature**:

```python
def merge_memory_results(
    serena_results: list[MemoryResult] | None = None,
    forgetful_results: list[MemoryResult] | None = None,
    max_results: int = 10,
) -> list[MemoryResult]
```

---

### test_forgetful_available

Checks whether Forgetful MCP is reachable, with 30 second caching.

**Signature**:

```python
def test_forgetful_available(port: int = 8020, force: bool = False) -> bool
```

**Side effect**: updates the health check cache, TTL 30 seconds. Pass `force=True` to skip the cache.

**Example**:

```python
if test_forgetful_available():
    print("Forgetful is available")
```

---

### get_memory_router_status

Diagnostic information about the router.

**Signature**:

```python
def get_memory_router_status() -> dict[str, Any]
```

**Returns** a dict shaped like this. Note the top level uses capitalized keys while `Configuration` uses snake_case, which is a real quirk of the current implementation:

```python
{
    "Serena": {"Available": True, "Path": ".serena/memories"},
    "Forgetful": {"Available": False, "Endpoint": "http://localhost:8020/mcp"},
    "Cache": {"AgeSeconds": 0.0, "TTLSeconds": 30.0},
    "Configuration": {
        "serena_path": ".serena/memories",
        "forgetful_port": 8020,
        "forgetful_timeout": 0.5,
        "max_results": 10,
    },
}
```

`forgetful_timeout` is in seconds, not milliseconds.

**Example**:

```python
status = get_memory_router_status()
print(status["Serena"]["Available"], status["Forgetful"]["Available"])
```

---

### get_content_hash

Returns the SHA-256 hash of a string as 64 lowercase hex characters. Used for deduplication.

```python
def get_content_hash(content: str) -> str
```

---

### reset_caches

Clears the health check and file listing caches. Tests call this between cases.

```python
def reset_caches() -> None
```

---

## reflexion_memory Module

### get_episode

Retrieves one episode by session id.

**Signature**:

```python
def get_episode(session_id: str) -> dict[str, Any] | None
```

**Parameters**:

- **session_id** (`str`, required): for example `"2026-01-01-session-126"`.

**Returns**: the episode dict, or `None` when no episode file exists.

**Raises**: `ValueError` when the resolved path escapes the episodes directory.

**Episode keys**:

- `id` (`str`): episode identifier
- `session` (`str`): source session id
- `timestamp` (`str`): ISO 8601
- `outcome` (`str`): `"success"`, `"partial"`, or `"failure"`
- `task` (`str`): high-level task description
- `decisions` (`list`): decision objects
- `events` (`list`): event objects
- `metrics` (`dict`): performance metrics
- `lessons` (`list`): lessons learned

**Example**:

```python
episode = get_episode("2026-01-01-session-126")
if episode:
    print(episode["outcome"])
```

---

### get_episodes

Retrieves episodes matching criteria.

**Signature**:

```python
def get_episodes(
    outcome: str | None = None,
    task: str | None = None,
    since: datetime | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]
```

**Parameters**:

- **outcome** (`str | None`): `"success"`, `"partial"`, or `"failure"`.
- **task** (`str | None`): substring match on the task field, case-insensitive.
- **since** (`datetime | None`): only episodes at or after this time.
- **max_results** (`int`): 1-100. Default 20.

**Returns**: episode dicts sorted by timestamp, newest first.

**Raises**: `ValueError` on an unknown `outcome` or an out-of-range `max_results`.

**Example**:

```python
from datetime import datetime, timedelta, timezone

failures = get_episodes(
    outcome="failure",
    since=datetime.now(timezone.utc) - timedelta(days=7),
)
```

---

### new_episode

Creates an episode from structured data and writes it to disk.

**Signature**:

```python
def new_episode(
    session_id: str,
    task: str,
    outcome: str,
    decisions: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    lessons: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    skip_validation: bool = False,
) -> dict[str, Any]
```

**Side effect**: writes `.agents/memory/episodes/episode-{session_id}.json`.

**Raises**: `ValueError` on an invalid outcome or a schema validation failure, `OSError` on a write failure.

`skip_validation` exists for tests. Do not set it in production code.

**Example**:

```python
episode = new_episode(
    session_id="2026-01-01-session-130",
    task="Implement feature X",
    outcome="success",
    lessons=["Lesson 1", "Lesson 2"],
)
```

---

### get_decision_sequence

Retrieves the decision sequence from an episode.

**Signature**:

```python
def get_decision_sequence(episode_id: str) -> list[dict[str, Any]]
```

**Parameters**:

- **episode_id** (`str`, required): for example `"episode-2026-01-01-session-126"`. The `episode-` prefix is stripped before lookup, so the session id also works.

**Returns**: decision dicts sorted by timestamp. Empty list when the episode does not exist.

**Example**:

```python
for d in get_decision_sequence("episode-2026-01-01-session-126"):
    print(d["timestamp"], d["chosen"])
```

---

### get_reflexion_memory_status

**Signature**:

```python
def get_reflexion_memory_status() -> dict[str, Any]
```

**Returns**:

```python
{
    "Episodes": {"Path": "/abs/path/.agents/memory/episodes", "Count": 322},
    "Configuration": {"EpisodesPath": "/abs/path/.agents/memory/episodes"},
}
```

**Example**:

```python
print(get_reflexion_memory_status()["Episodes"]["Count"])
```

---

## Scripts

### search_memory.py

Command line wrapper over `memory_router`.

```bash
uv run python .claude/skills/memory/scripts/search_memory.py <query> \
    [--max-results N] [--lexical-only | --semantic-only] \
    [--format json|table] [--serena-path PATH] [--episodes-path PATH]
```

Unlike `memory_router.search_memory`, this script also searches the episode store.

### extract_session_episode.py

Extracts episode data from a session log.

```bash
uv run python .claude/skills/memory/scripts/extract_session_episode.py <session-log-path> \
    [--output-path DIR] [--force | --preserve] [--pending-stage]
```

**Parameters**:

- **session_log_path** (required, positional): path to the session log. Must exist.
- **--output-path**: output directory. Default `.agents/memory/episodes/`.
- **--force**: overwrite an existing episode file.
- **--preserve**: merge fresh extraction over an existing file rather than replacing it.

**Exit codes**:

- `0`: success
- `1`: failed to read the session log, failed to write the episode, or the episode exists and neither `--force` nor `--preserve` was given

**Example**:

```bash
uv run python .claude/skills/memory/scripts/extract_session_episode.py \
    .agents/sessions/2026-01-01-session-126.json
```

---

## Data Types

### Decision Object

```python
{
    "id": "d001",                        # str: decision id
    "timestamp": "2026-01-01T17:05:00Z", # str: ISO 8601
    "type": "design",                    # str: design|implementation|test|recovery|routing
    "context": "Choosing routing",       # str: decision context
    "chosen": "Serena-first",            # str: chosen option
    "rationale": "Lower latency",        # str: rationale
    "outcome": "success",                # str: success|partial|failure
    "effects": ["d002", "d003"],         # list[str]: affected decision or event ids
}
```

### Event Object

```python
{
    "id": "e001",                        # str: event id
    "timestamp": "2026-01-01T17:10:00Z", # str: ISO 8601
    "type": "commit",                    # str: tool_call|commit|error|milestone|test|handoff
    "content": "Created module",         # str: event description
    "caused_by": ["d001"],               # list[str]: causing decision ids
    "leads_to": ["e002"],                # list[str]: resulting event ids
}
```

### Metrics Object

```python
{
    "duration_minutes": 45,  # int: session duration
    "tool_calls": 87,        # int: tool invocations
    "errors": 2,             # int: error count
    "recoveries": 2,         # int: recovery count
    "commits": 3,            # int: commit count
    "files_changed": 8,      # int: files modified
}
```

---

## Error Handling

- Invalid input raises `ValueError`. Read failures raise `OSError`. A required-but-unavailable Forgetful raises `RuntimeError`.
- Not-found is not an error. `get_episode` returns `None`; `get_decision_sequence` and `get_episodes` return empty lists.
- Recoverable problems are reported through the `logging` module, not by raising.

---

## Performance Characteristics

| Function | Typical latency | Complexity |
|----------|----------------|------------|
| `search_memory` (Serena only) | 530ms | O(n) file scan |
| `search_memory` (augmented) | 700ms | O(n) + network |
| `test_forgetful_available` (cached) | <1ms | O(1) cache read |
| `test_forgetful_available` (fresh) | 1-500ms | TCP connect |
| `get_memory_router_status` | <10ms | file stats + cache read |
| `get_episode` | <50ms | JSON file read |
| `get_episodes` | ~200ms | O(n) directory scan |
| `new_episode` | ~100ms | JSON serialize + write |
| `get_reflexion_memory_status` | <50ms | file stats |

Latencies assume SSD storage and a hot filesystem cache.

---

## Related Documentation

- [Memory Router](memory-router.md). Detailed router usage.
- [Reflexion Memory](../../memory-reflexion/references/reflexion-memory.md). Detailed episode usage.
- [Benchmarking](../../memory-maintenance/references/benchmarking.md). Performance measurement.
- [Quick Start Guide](quick-start.md). Common usage patterns.
- ADR-037. Memory Router architecture.
- ADR-038. Reflexion Memory schema.
- ADR-042. Python-first scripting.

<!-- vendor-portability: declared. This API reference documents Python defaults that write episodes to .agents/memory/episodes/. That is a configurable output path (--output-path); a vendored install overrides it or lets the tool create the default dir. Issue #2050. -->
