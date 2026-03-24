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
from reflexion_memory import get_episodes, get_patterns

# 1. Search memory for relevant patterns
array_patterns = search_memory(query="arrays", max_results=5)

# 2. Review past failures in similar scenarios
past_failures = [
    ep for ep in get_episodes(outcome="failure")
    if "array" in ep["task"]
]

# 3. Check for known patterns
patterns = get_patterns(min_success_rate=0.7, min_occurrences=2)

# 4. Make informed decision based on memory
# ... your agent logic here ...
```

### Check for Anti-Patterns

```python
from reflexion_memory import get_anti_patterns

# Before implementing a solution, check for known anti-patterns
anti_patterns = get_anti_patterns(max_success_rate=0.3)

for ap in anti_patterns:
    print(f"AVOID: {ap['name']}")
    print(f"  Failure rate: {(1 - ap['success_rate']) * 100:.0f}%")
    print(f"  Trigger: {ap['trigger']}")
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
# Use mcp__serena__list_memories() or mcp__forgetful__execute_forgetful_tool("query_memory", {...})
```

### Extract Episode from Session

```bash
# After completing a session
python3 .claude/skills/memory/scripts/extract_session_episode.py \
    --session-log-path ".agents/sessions/.agents/sessions/2026-01-01-session-130.json"

# Update causal graph
python3 .claude/skills/memory/scripts/update_causal_graph.py
```

## Common Patterns

### Pattern 1: Memory-First Decision Making

```python
from memory_router import search_memory
from reflexion_memory import get_patterns, get_episodes

# Step 1: Search for relevant knowledge
knowledge = search_memory(query="topic", max_results=5)

# Step 2: Check for proven patterns
patterns = [
    p for p in get_patterns(min_success_rate=0.7)
    if "topic" in p["trigger"] or "topic" in p["action"]
]

# Step 3: Review past attempts
past_attempts = [ep for ep in get_episodes() if "topic" in ep["task"]]

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

### Pattern 3: Pattern Library Maintenance

```python
from reflexion_memory import get_patterns

# Get all patterns
all_patterns = get_patterns()

# Categorize by success rate
high_success = [p for p in all_patterns if p["success_rate"] >= 0.8]
medium_success = [p for p in all_patterns if 0.5 <= p["success_rate"] < 0.8]
low_success = [p for p in all_patterns if p["success_rate"] < 0.5]

print("=== Pattern Library Summary ===")
print(f"High Success (>=80%): {len(high_success)}")
print(f"Medium Success (50-79%): {len(medium_success)}")
print(f"Low Success (<50%): {len(low_success)}")

# Review low success patterns for archival
for pattern in low_success:
    print(f"\n{pattern['name']}:")
    print(f"  Success: {pattern['success_rate'] * 100:.0f}%")
    print(f"  Uses: {pattern['occurrences']}")
    print("  Consider: Archival or revision")
```

### Pattern 4: Causal Tracing

```python
from reflexion_memory import get_causal_path

# Find causal path from decision to outcome
path = get_causal_path(
    from_label="routing strategy",
    to_label="performance target met",
    max_depth=5,
)

if path["found"]:
    print(f"Causal chain ({path['depth']} steps):")
    for i, node in enumerate(path["path"]):
        print(f"  {i + 1}. {node['label']} ({node['type']})")

        # Show success rate
        if node.get("success_rate"):
            print(f"     Success rate: {node['success_rate'] * 100:.0f}%")
else:
    print(f"No causal path found: {path['error']}")
```

### Pattern 5: Session End Workflow

```bash
# Complete at end of every session

SESSION_ID="2026-01-01-session-130"
SESSION_LOG=".agents/sessions/${SESSION_ID}.md"

# 1. Extract episode from session log
python3 .claude/skills/memory/scripts/extract_session_episode.py \
    --session-log-path "$SESSION_LOG"

# 2. Update causal graph
python3 .claude/skills/memory/scripts/update_causal_graph.py \
    --episode-path ".agents/memory/episodes/episode-${SESSION_ID}.json"
```

```python
from reflexion_memory import get_episode, get_reflexion_memory_status

# 3. Verify extraction
episode = get_episode(session_id="2026-01-01-session-130")

print("Episode verified:")
print(f"  Outcome: {episode['outcome']}")
print(f"  Decisions: {len(episode['decisions'])}")
print(f"  Events: {len(episode['events'])}")
print(f"  Lessons: {len(episode['lessons'])}")

# 4. Check causal graph update
status = get_reflexion_memory_status()
print("\nCausal graph:")
print(f"  Nodes: {status['causal_graph']['nodes']}")
print(f"  Edges: {status['causal_graph']['edges']}")
print(f"  Patterns: {status['causal_graph']['patterns']}")
```

## Integration with Session Protocol

### Session Start

```python
from datetime import datetime, timedelta
from memory_router import search_memory
from reflexion_memory import get_episodes

# Required step in SESSION-PROTOCOL.md

# 1. Read usage-mandatory memory
mandatory = search_memory(query="usage-mandatory", lexical_only=True)

# 2. Search for relevant project memories
project_context = search_memory(query="project phase 2A", max_results=10)

# 3. Review recent episodes
since = datetime.now() - timedelta(days=7)
recent_episodes = get_episodes(since=since, max_results=5)

# Now proceed with session work...
```

### Session End

```bash
# Required step in SESSION-PROTOCOL.md

# 1. Extract episode
python3 .claude/skills/memory/scripts/extract_session_episode.py \
    --session-log-path ".agents/sessions/$(date +%Y-%m-%d)-session-*.md"

# 2. Update causal graph
python3 .claude/skills/memory/scripts/update_causal_graph.py

# 3. Commit changes (including episodes and causality)
git add .agents/memory/episodes/ .agents/memory/causality/
git commit -m "session: Extract episode and update causal graph"
```

## Performance Optimization

### When to Use LexicalOnly

```python
from memory_router import search_memory

# Use lexical_only when:
# - Forgetful is unavailable
# - Performance is critical
# - Exact keyword matching is needed

results = search_memory(query="exact term", lexical_only=True)
```

### When to Use SemanticOnly

```python
from memory_router import search_memory

# Use semantic_only when:
# - Need conceptual similarity
# - Keywords are ambiguous
# - Exploring related topics

try:
    results = search_memory(query="authentication security", semantic_only=True)
except RuntimeError:
    print("WARNING: Forgetful unavailable, falling back to lexical")
    results = search_memory(query="authentication security", lexical_only=True)
```

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
            --session-log-path "$SESSION_LOG"
    fi
fi
```

### Forgetful Not Available

```python
from memory_router import test_forgetful_available, search_memory

# Check Forgetful health
available = test_forgetful_available(force=True)

if not available:
    print("WARNING: Forgetful not available")
    print("Solutions:")
    print("  1. Start Forgetful: systemctl --user start forgetful")
    print("  2. Check port: ss -tlnp | grep 8020")
    print("  3. Use lexical_only: search_memory(query='test', lexical_only=True)")
```

## Best Practices

### For Agents

1. **Always search before deciding**: Use `search_memory()` at task start
2. **Check patterns**: Use `get_patterns()` to find proven approaches
3. **Avoid anti-patterns**: Use `get_anti_patterns()` before implementing
4. **Learn from failures**: Query past failures for similar scenarios
5. **Record decisions**: Ensure episodes capture decision rationale

### For Session Management

1. **Extract episodes immediately**: Don't delay until later sessions
2. **Update causal graph regularly**: Run after each episode extraction
3. **Review patterns weekly**: Check for new high-success patterns
4. **Prune stale data**: Archive low-frequency nodes periodically
5. **Commit with context**: Include episode/graph updates in session commits

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
from reflexion_memory import get_patterns, get_episodes

# 1. Search for similar features
similar = search_memory(query="feature implementation patterns", max_results=10)

# 2. Check proven design patterns
patterns = [
    p for p in get_patterns(min_success_rate=0.8)
    if "design" in p["trigger"] or "architecture" in p["action"]
]

# 3. Review past feature implementations
past_features = [
    ep for ep in get_episodes()
    if "implement" in ep["task"] and ep["outcome"] == "success"
]

# 4. Implement with full context
# ... implementation ...
```

### Use Case: Debugging Issue

```python
from memory_router import search_memory
from reflexion_memory import get_episodes, get_patterns

# 1. Search for error patterns
error_patterns = search_memory(query="error message text", max_results=5)

# 2. Find past similar errors
past_errors = [
    ep for ep in get_episodes()
    if any(e["type"] == "error" and "error pattern" in e["content"]
           for e in ep["events"])
]

# 3. Check recovery patterns
recoveries = [
    p for p in get_patterns()
    if "error pattern" in p["trigger"]
]

# 4. Apply recovery strategy
# ... debugging ...
```

### Use Case: Code Review

```python
from memory_router import search_memory
from reflexion_memory import get_anti_patterns, get_episodes

# 1. Search for coding standards
standards = search_memory(query="code style guidelines", max_results=5)

# 2. Check for anti-patterns in code
anti_patterns = get_anti_patterns()

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
- [Benchmarking Guide](benchmarking.md) - Performance measurement
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
