# Reflexion Memory
<!-- # taste-lint: ignore file-size -->
<!-- file-size rationale: reference doc for the memory API; every entry
documents a real entry point verified by test_reference_docs_resolve.py,
and splitting the reference breaks lookup by single file. -->

<!-- vendor-portability: declared. This reference documents upstream memory artifact paths under .agents/memory/ for the episodic memory schema. It is reference material only; runtime writes stay in the canonical memory scripts and their path helpers. Issue #2050. -->

## Overview

The Reflexion Memory module (`.claude/skills/memory/memory_core/reflexion_memory.py`) provides episodic replay. This implements Tier 2 of the memory architecture.

The query API is Python. The repository ships no PowerShell: `git ls-files '*.ps1' '*.psm1'` returns zero files, and ADR-042 makes Python the only scripting language for new work.

`.claude/skills/memory/scripts/extract_session_episode.py` is the writer that turns a session log into an episode.

ADR-089 removed the Tier 3 derived causal graph this module once maintained: nothing read it, and its aggregated output was noise. Episodes are unaffected and remain the system of record.

**ADR**: ADR-038 Reflexion Memory Schema, ADR-089 Causal Tier Removal

**Task**: M-005 (Phase 2A Memory System)

## Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                   Episodic Memory (Tier 2)                    │
│      Session transcripts, decision sequences, outcomes        │
│                    (.agents/memory/episodes/)                        │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
        No code reads these files today. The query API has no
        caller outside its own module, its tests, and doc
        examples. Tracked in issue 3630.
```

## Core Concepts

### Episodic Memory

Episodes are structured extracts from session logs, optimized for replay and analysis.

**Key Features**:

- Decision sequences with timestamps
- Event chains (commits, errors, milestones)
- Outcome classification (success, partial, failure)
- Metrics (duration, tool calls, errors, recoveries)
- Lessons learned

**Token Efficiency**: Episodes are 500-2000 tokens vs 10K-50K tokens for full session logs.

## Storage Formats

### Episode Schema

**Location**: `.agents/memory/episodes/episode-{session-id}.json`

```json
{
  "id": "episode-2026-01-01-session-126",
  "session": "2026-01-01-session-126",
  "timestamp": "2026-01-01T17:00:00Z",
  "outcome": "success",
  "task": "Implement MemoryRouter module",
  "decisions": [
    {
      "id": "d001",
      "timestamp": "2026-01-01T17:05:00Z",
      "type": "design",
      "context": "Choosing routing strategy",
      "chosen": "Serena-first routing",
      "rationale": "Lower latency, no network dependency",
      "outcome": "success",
      "effects": ["d002", "d003"]
    }
  ],
  "events": [
    {
      "id": "e001",
      "timestamp": "2026-01-01T17:10:00Z",
      "type": "commit",
      "content": "Created memory_router module (search_memory.py)",
      "caused_by": ["d001"],
      "leads_to": ["e002"]
    }
  ],
  "metrics": {
    "duration_minutes": 45,
    "tool_calls": 87,
    "errors": 2,
    "recoveries": 2,
    "commits": 3,
    "files_changed": 8
  },
  "lessons": [
    "Pre-commit hooks check all markdown, not just staged files",
    "When a hook fails on unrelated files, fix the validator or open an issue; do not bypass hooks with --no-verify"
  ]
}
```

## Usage

`memory_core` is a package under the memory skill, not an installed distribution. Put the skill root on `sys.path` first:

```python
import os
import sys
_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".claude"
sys.path.insert(0, f"{_root}/skills/memory")

from memory_core.reflexion_memory import (
    get_episode,
    get_episodes,
    new_episode,
    get_decision_sequence,
    get_reflexion_memory_status,
)
```

### Episode Queries

```python
from datetime import datetime, timedelta, timezone

episode = get_episode("2026-01-01-session-126")

failures = get_episodes(
    outcome="failure",
    since=datetime.now(timezone.utc) - timedelta(days=7),
)

successes = get_episodes(outcome="success", max_results=50)

decisions = get_decision_sequence("episode-2026-01-01-session-126")
```

### System Status

```python
status = get_reflexion_memory_status()
print(f"Episodes: {status['Episodes']['Count']} in {status['Episodes']['Path']}")
```

## Functions

### Episode Functions

#### get_episode

Retrieves an episode by session id.

**Signature**:

```python
def get_episode(session_id: str) -> dict[str, Any] | None
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | `str` | Yes | Session identifier, for example `"2026-01-01-session-126"` |

**Returns**: the episode dict, or `None` when no episode file exists.

**Raises**: `ValueError` when the resolved path escapes the episodes directory.

**Example**:

```python
episode = get_episode("2026-01-01-session-126")
if episode:
    print(f"Task: {episode['task']}")
    print(f"Outcome: {episode['outcome']}")
    print(f"Decisions: {len(episode['decisions'])}")
```

#### get_episodes

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

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `outcome` | `str \| None` | No | `None` | Filter by outcome: `success`, `partial`, `failure` |
| `task` | `str \| None` | No | `None` | Substring match on the task field, case-insensitive |
| `since` | `datetime \| None` | No | `None` | Only episodes at or after this time |
| `max_results` | `int` | No | 20 | Maximum episodes to return, 1-100 |

**Returns**: episode dicts sorted by timestamp, newest first.

**Raises**: `ValueError` on an unknown `outcome` or an out-of-range `max_results`.

**Example**:

```python
from datetime import datetime, timedelta, timezone

failures = get_episodes(
    outcome="failure",
    since=datetime.now(timezone.utc) - timedelta(days=7),
)

for ep in failures:
    print(f"{ep['session']}: {ep['task']} - {len(ep['lessons'])} lessons learned")
```

#### new_episode

Creates a new episode from structured data.

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

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | - | Source session identifier |
| `task` | `str` | Yes | - | High-level task description |
| `outcome` | `str` | Yes | - | `success`, `partial`, or `failure` |
| `decisions` | `list[dict] \| None` | No | `None` | Decision objects |
| `events` | `list[dict] \| None` | No | `None` | Event objects |
| `lessons` | `list[str] \| None` | No | `None` | Lesson strings |
| `metrics` | `dict \| None` | No | `None` | Metrics dict |
| `skip_validation` | `bool` | No | `False` | Skip schema validation. Tests only. |

**Returns**: the episode dict. Also writes `.agents/memory/episodes/episode-{session_id}.json`.

**Raises**: `ValueError` on an invalid outcome or a schema validation failure, `OSError` on a write failure.

**Example**:

```python
from datetime import datetime, timezone

episode = new_episode(
    session_id="2026-01-01-session-130",
    task="Implement feature X",
    outcome="success",
    decisions=[
        {
            "id": "d001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "design",
            "context": "Choosing architecture",
            "chosen": "Event-driven design",
            "rationale": "Better scalability",
            "outcome": "success",
            "effects": [],
        }
    ],
    lessons=["Event-driven design reduced coupling"],
)
```

#### get_decision_sequence

Retrieves the decision sequence from an episode.

**Signature**:

```python
def get_decision_sequence(episode_id: str) -> list[dict[str, Any]]
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `episode_id` | `str` | Yes | Episode identifier, for example `"episode-2026-01-01-session-126"`. The `episode-` prefix is stripped before lookup, so the session id also works. |

**Returns**: decision dicts sorted by timestamp. Empty list when the episode does not exist.

**Example**:

```python
for d in get_decision_sequence("episode-2026-01-01-session-126"):
    print(f"{d['timestamp']}: {d['type']} - {d['chosen']}")
```

### Status Functions

#### get_reflexion_memory_status

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
status = get_reflexion_memory_status()
print("=== Reflexion Memory Status ===")
print(f"  Path:  {status['Episodes']['Path']}")
print(f"  Count: {status['Episodes']['Count']}")
```

## Scripts

### extract_session_episode.py

Extracts episode data from session logs.

**Syntax**:

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" <session-log-path> \
    [--output-path DIR] [--force | --preserve] [--pending-stage]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_log_path` | path | Yes | - | Positional. Path to the session log file |
| `--output-path` | path | No | `.agents/memory/episodes/` | Output directory for episode JSON |
| `--force` | flag | No | - | Overwrite an existing episode file |
| `--preserve` | flag | No | - | Merge fresh extraction over an existing episode. Mutually exclusive with `--force` |
| `--pending-stage` | flag | No | - | Count the not-yet-staged episode file in the staged-file total |

**Extraction Targets**:

- Session metadata (date, objectives, status)
- Decisions made during the session
- Events (commits, errors, milestones, tests)
- Metrics (duration, file counts, errors, recoveries)
- Lessons learned

**Example**:

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" \
    .agents/sessions/2026-01-01-session-126.json

# Output:
# Episode extracted:
#   ID:        episode-2026-01-01-session-126
#   Session:   2026-01-01-session-126
#   Outcome:   success
#   Decisions: 5
#   Events:    12
#   Lessons:   3
#   Output:    .agents/memory/episodes/episode-2026-01-01-session-126.json
```

## Integration

### With Retrospective Agent

The retrospective agent auto-extracts episodes at session end:

```bash
SESSION_LOG=".agents/sessions/${SESSION_ID}.json"

uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" "$SESSION_LOG"
```

### With Session Protocol

Session log creation is discontinued. Episode extraction from a session log
now applies only when one already exists on the branch (carried over from
before the discontinuation, or cherry-picked from an older one):

```markdown
## Session End (BLOCKING)

- [ ] Update the per-issue handoff
- [ ] Extract episode if a session log exists: `.claude/skills/memory/scripts/extract_session_episode.py`
- [ ] Update Serena memory
- [ ] Commit all changes (including .agents/memory/episodes/)
```

### With Memory Router

`memory_router.search_memory` covers Serena only. The episode store is searched by the CLI wrapper:

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "routing decision"
```

## Use Cases

### Review Past Failures

```python
from datetime import datetime, timedelta, timezone

failures = get_episodes(
    outcome="failure",
    since=datetime.now(timezone.utc) - timedelta(days=30),
)

for failure in failures:
    print(f"\n=== {failure['session']} ===")
    print(f"Task: {failure['task']}")
    print("\nLessons Learned:")
    for lesson in failure["lessons"]:
        print(f"  - {lesson}")

    errors = [e for e in failure["events"] if e["type"] == "error"]
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err['content']}")
```

### Compare Decision Outcomes

```python
from collections import Counter

routing = [
    ep
    for ep in get_episodes(max_results=100)
    if any("routing" in d.get("context", "") for d in ep["decisions"])
]

by_outcome: dict[str, list[dict]] = {}
for ep in routing:
    by_outcome.setdefault(ep["outcome"], []).append(ep)

for outcome, episodes in by_outcome.items():
    print(f"{outcome}: {len(episodes)} episodes")
    chosen = Counter(
        d["chosen"]
        for ep in episodes
        for d in ep["decisions"]
        if "routing" in d.get("context", "")
    )
    for choice, count in chosen.most_common():
        print(f"  - {choice}: {count} times")
```

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| `get_episode` | <50ms | Single JSON file read |
| `get_episodes` | ~200ms | O(n) scan of the episode directory |
| `get_decision_sequence` | <10ms | Single read plus an in-memory sort |
| `extract_session_episode.py` | ~500ms | Parse the session log, extract structured data |

## Best Practices

### For Agents

1. **Learn from failures**: query `get_episodes(outcome="failure")` for similar scenarios.

### For Episode Extraction

1. **Run at session end**: extract episodes while the session is fresh.
2. **Validate extraction**: check the episode JSON for completeness.
3. **Commit with the session**: include episodes in the session commit.

## Troubleshooting

### Episode Not Found

**Symptoms**: `get_episode` returns `None`.

**Solutions**:

1. Verify the episode file exists: `ls .agents/memory/episodes/episode-<session-id>.json`
2. Check the session id format. It must match the file naming convention.
3. Re-extract from the session log with `extract_session_episode.py`.

## Related Documentation

- [Memory Router](../../memory-search/references/memory-router.md). Tier 1 semantic memory (Serena).
- [Benchmarking](../../memory-maintenance/references/benchmarking.md). Performance measurement.
- [API Reference](../../memory-search/references/api-reference.md). Complete function signatures.
- ADR-038. Reflexion Memory schema.
- ADR-007. Memory-first architecture.
- ADR-042. Python-first scripting.
