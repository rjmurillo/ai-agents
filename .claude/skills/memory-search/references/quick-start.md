# Memory System Quick Start Guide

## Overview

This guide provides common usage patterns for the ai-agents memory system (v0.2.0). Follow these examples to get started quickly.

## For AI Agents

### Basic Memory Search

```python
from memory_router import search_memory

# Search for relevant knowledge before making decisions
results = search_memory(query="array handling", max_results=5)

# Process results
for result in results:
    print(f"=== {result['name']} (Source: {result['source']}) ===")
    print(result["content"])
    print()
```

**Use When**: Starting any non-trivial task, before making technical decisions.

### Agent Workflow Example

```python
from memory_router import search_memory
from reflexion_memory import get_episodes

# 1. Search memory for relevant knowledge
array_knowledge = search_memory(query="arrays", max_results=5)

# 2. Review past failures in similar scenarios
past_failures = [
    ep for ep in get_episodes(outcome="failure")
    if "array" in ep["task"]
]

# 3. Read the lessons those failures recorded
lessons = [lesson for ep in past_failures for lesson in ep["lessons"]]

# 4. Make informed decision based on memory
# ... your agent logic here ...
```

### Check What Failed Before

```python
from reflexion_memory import get_episodes

# Before implementing a solution, read the lessons from past failures
for episode in get_episodes(outcome="failure"):
    print(f"AVOID: {episode['task']}")
    for lesson in episode["lessons"]:
        print(f"  Lesson: {lesson}")
    print()
```

## For Human Users

### Search via Skill Script

```bash
# Basic search with JSON output
python3 .claude/skills/memory/scripts/search_memory.py \
    --query "git hooks" \
    --format json

# Table format for quick review
python3 .claude/skills/memory/scripts/search_memory.py \
    --query "session protocol" \
    --format table
```

### Check System Status

```bash
# Run comprehensive health check (recommended)
python3 .claude/skills/memory/scripts/test_memory_health.py --format table

# Memory Router status (via MCP tools)
# Use mcp__serena__list_memories()
```

### Extract Episode from Session

```bash
# After completing a session
python3 .claude/skills/memory/scripts/extract_session_episode.py \
    ".agents/sessions/2026-01-01-session-130.json"
```

## Common Patterns

### Pattern 1: Memory-First Decision Making

```python
from memory_router import search_memory
from reflexion_memory import get_episodes

# Step 1: Search for relevant knowledge
knowledge = search_memory(query="topic", max_results=5)

# Step 2: Review past attempts
past_attempts = [ep for ep in get_episodes() if "topic" in ep["task"]]

# Step 3: Read what those attempts concluded
lessons = [lesson for ep in past_attempts for lesson in ep["lessons"]]

# Step 4: Make decision with full context
# ... decision logic ...

# Step 5: Record decision in episode (at session end)
```

### Pattern 2: Failure Analysis

```python
from datetime import datetime, timedelta
from reflexion_memory import get_episodes

# Get recent failures
since = datetime.now() - timedelta(days=30)
failures = get_episodes(outcome="failure", since=since)

for failure in failures:
    print(f"\n=== {failure['session']} ===")
    print(f"Task: {failure['task']}")

    # Extract lessons
    print("\nLessons:")
    for lesson in failure["lessons"]:
        print(f"  - {lesson}")

    # Find error events
    errors = [e for e in failure["events"] if e["type"] == "error"]
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err['content']}")

    # Find recovery decisions
    recoveries = [d for d in failure["decisions"] if d["type"] == "recovery"]
    if recoveries:
        print("\nRecoveries Attempted:")
        for rec in recoveries:
            print(f"  - {rec['chosen']} (Outcome: {rec['outcome']})")
```

### Pattern 3: Episode Inventory

```python
from reflexion_memory import get_episodes

all_episodes = get_episodes()

by_outcome: dict[str, int] = {}
for episode in all_episodes:
    outcome = episode.get("outcome", "unknown")
    by_outcome[outcome] = by_outcome.get(outcome, 0) + 1

print("=== Episode Inventory ===")
print(f"Total: {len(all_episodes)}")
for outcome, count in sorted(by_outcome.items()):
    print(f"  {outcome}: {count}")

# Episodes with no lessons carry no reusable signal
empty = [ep for ep in all_episodes if not ep["lessons"]]
print(f"Episodes with no recorded lessons: {len(empty)}")
```

### Pattern 4: Session End Workflow

```bash
# Complete at end of every session

SESSION_ID="2026-01-01-session-130"
SESSION_LOG=".agents/sessions/${SESSION_ID}.md"

# 1. Extract episode from session log
python3 .claude/skills/memory/scripts/extract_session_episode.py \
    "$SESSION_LOG"

```

```python
from reflexion_memory import get_episode, get_reflexion_memory_status

# 2. Verify extraction
episode = get_episode(session_id="2026-01-01-session-130")

print("Episode verified:")
print(f"  Outcome: {episode['outcome']}")
print(f"  Decisions: {len(episode['decisions'])}")
print(f"  Events: {len(episode['events'])}")
print(f"  Lessons: {len(episode['lessons'])}")

# 3. Check the episode store
status = get_reflexion_memory_status()
print(f"\nEpisodes on disk: {status['episodes']['count']}")
```

## Integration with Session Protocol

### Session Start

```python
from datetime import datetime, timedelta
from memory_router import search_memory
from reflexion_memory import get_episodes

# 1. Read usage-mandatory memory
mandatory = search_memory(query="usage-mandatory")

# 2. Search for relevant project memories
project_context = search_memory(query="project phase 2A", max_results=10)

# 3. Review recent episodes
since = datetime.now() - timedelta(days=7)
recent_episodes = get_episodes(since=since, max_results=5)

# Now proceed with session work...
```

### Session End

```bash
# 1. Extract episode
python3 .claude/skills/memory/scripts/extract_session_episode.py \
    ".agents/sessions/$(date +%Y-%m-%d)-session-*.md"

# 2. Commit the episode
git add .agents/memory/episodes/
git commit -m "session: Extract episode"
```

## Performance Optimization

### Caching Results

```python
from functools import lru_cache
from memory_router import search_memory

@lru_cache(maxsize=64)
def get_cached_memory(query: str) -> list:
    """Cache frequently accessed memories within a session."""
    return search_memory(query=query)

# Use cached results
results = get_cached_memory("array handling patterns")
```

## Troubleshooting

### No Results from Search

```python
from pathlib import Path
from memory_router import get_memory_router_status, search_memory

# Check system status first
status = get_memory_router_status()

if not status["serena"]["available"]:
    raise RuntimeError(f"Serena not available at: {status['serena']['path']}")

# Verify memory files exist
memory_path = Path(status["serena"]["path"])
memory_count = len(list(memory_path.glob("*.md")))
print(f"Memory files: {memory_count}")

# Try broader query
results = search_memory(query="general topic", max_results=20)
```

### Episode Not Found

```bash
# Check if episode file exists
EPISODE_PATH=".agents/memory/episodes/episode-2026-01-01-session-126.json"
if [ ! -f "$EPISODE_PATH" ]; then
    echo "WARNING: Episode not extracted yet"

    # Extract from session log
    SESSION_LOG=".agents/sessions/2026-01-01-session-126.json"
    if [ -f "$SESSION_LOG" ]; then
        python3 .claude/skills/memory/scripts/extract_session_episode.py \
            "$SESSION_LOG"
    fi
fi
```

## Best Practices

### For Agents

1. **Always search before deciding**: Use `search_memory()` at task start
2. **Check past episodes**: Use `get_episodes()` to find prior attempts
3. **Read the lessons**: Review `episode["lessons"]` before implementing
4. **Learn from failures**: Query past failures for similar scenarios
5. **Record decisions**: Ensure episodes capture decision rationale

### For Session Management

1. **Extract episodes immediately**: Don't delay until later sessions
2. **Review lessons weekly**: Read what recent episodes concluded
3. **Commit with context**: Include the episode file in the session commit

### For Memory Queries

1. **Use specific queries**: "array handling patterns" not "arrays"
2. **Limit results**: Use `max_results` to avoid information overload
3. **Try both modes**: Compare lexical vs semantic for ambiguous queries
4. **Cache frequent queries**: Reuse results within a session
5. **Check availability**: Use `get_memory_router_status()` if queries fail

## Examples by Use Case

### Use Case: Implementing New Feature

```python
from memory_router import search_memory
from reflexion_memory import get_episodes

# 1. Search for similar features
similar = search_memory(query="feature implementation patterns", max_results=10)

# 2. Review past feature implementations that succeeded
past_features = [
    ep for ep in get_episodes()
    if "implement" in ep["task"] and ep["outcome"] == "success"
]

# 3. Read the design decisions those sessions recorded
decisions = [d for ep in past_features for d in ep["decisions"]]

# 4. Implement with full context
# ... implementation ...
```

### Use Case: Debugging Issue

```python
from memory_router import search_memory
from reflexion_memory import get_episodes

# 1. Search for the error text
error_knowledge = search_memory(query="error message text", max_results=5)

# 2. Find past similar errors
past_errors = [
    ep for ep in get_episodes()
    if any(e["type"] == "error" and "error pattern" in e["content"]
           for e in ep["events"])
]

# 3. Check what those sessions did to recover
recoveries = [
    d for ep in past_errors
    for d in ep["decisions"] if d["type"] == "recovery"
]

# 4. Apply recovery strategy
# ... debugging ...
```

### Use Case: Code Review

```python
from memory_router import search_memory
from reflexion_memory import get_episodes

# 1. Search for coding standards
standards = search_memory(query="code style guidelines", max_results=5)

# 2. Read the lessons past failures recorded
failure_lessons = [
    lesson for ep in get_episodes(outcome="failure") for lesson in ep["lessons"]
]

# 3. Review past code review findings
past_reviews = [
    ep for ep in get_episodes()
    if "review" in ep["task"] and len(ep["lessons"]) > 0
]

# 4. Perform review with context
# ... review ...
```

## Additional Resources

- [Full API Reference](api-reference.md) - Complete function signatures
- [Memory Router Documentation](memory-router.md) - Detailed Router usage
- [Reflexion Memory Documentation](reflexion-memory.md) - Detailed Reflexion usage
- [Benchmarking Guide](../../memory-maintenance/references/benchmarking.md) - Performance measurement
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
