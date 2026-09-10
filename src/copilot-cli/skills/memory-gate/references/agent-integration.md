# Agent Integration Guide

## Overview

This guide explains how AI agents integrate with the memory system. The memory system is designed to be consumed by agents through skills, direct module imports, and MCP tools.

## Integration Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     AI Agent (Claude)                        │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │   Task Agents  │  │  Orchestrator  │  │    Memory      │ │
│  │  (implementer, │  │     Agent      │  │     Agent      │ │
│  │   analyst...)  │  │                │  │                │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘ │
└──────────┼───────────────────┼───────────────────┼──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     Access Methods                           │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │  Skill Script  │  │  Python        │  │   MCP Tools    │ │
│  │  search_memory │  │   Module       │  │  Serena        │ │
│  │     .py        │  │   Import       │  │                │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘ │
└──────────┼───────────────────┼───────────────────┼──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Memory System                             │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                   Memory Router                         │ │
│  │                    (Serena)                             │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │                 Reflexion Memory                        │ │
│  │                 (Episodes, Tier 2)                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Access Methods

### Method 1: Skill Script (Recommended for Agents)

The primary interface for agents is `search_memory.py`. The query is a
positional argument; there is no `--query` flag.

```bash
# Basic search
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "git hooks"

# With options
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" \
    "shell array handling" \
    --max-results 5 \
    --format json
```

**Advantages**:

- Standardized interface
- Input validation
- JSON output for parsing
- Error handling with structured output

### Method 2: Python Module Import

For complex workflows requiring multiple operations. `memory_core` is a package
under the skill, not an installed distribution, so put the skill directory on
`sys.path` first.

```python
import os
import sys
_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".claude"
sys.path.insert(0, f"{_root}/skills/memory")

from memory_core.memory_router import search_memory
from memory_core.reflexion_memory import get_episodes

facts = search_memory("authentication", max_results=10)
past = get_episodes(task="authentication", max_results=5)
```

**Advantages**:

- Full API access
- Multiple operations without subprocess overhead
- Direct object manipulation

### Method 3: MCP Tools (Direct)

For direct MCP tool access:

```python
# Serena (file-based, always available)
mcp__serena__list_memories()
mcp__serena__read_memory(memory_file_name="powershell/powershell-array-handling")
mcp__serena__write_memory(memory_file_name="new-pattern", content="...")

```

**Advantages**:

- Native Claude tool integration
- No subprocess required
- Reads the committed corpus directly, with no service to be up

## Agent Workflows

### Workflow 1: Memory-First Decision Making

Per ADR-007, agents retrieve memory before reasoning:

```text
┌─────────────────────────────────────────────────────────────┐
│                    Agent Task Received                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Search Semantic Memory (Tier 1)                     │
│                                                              │
│  search_memory("[task topic]", max_results=10)               │
│                                                              │
│  → Retrieves relevant facts, patterns, rules                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Review Episodic Memory (Tier 2)                     │
│                                                              │
│  get_episodes(task="[topic]")                                │
│                                                              │
│  → Past decisions and their outcomes                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Execute with Full Context                           │
│                                                              │
│  Agent reasoning grounded in past learnings                  │
└─────────────────────────────────────────────────────────────┘
```

### Workflow 2: Learning from Sessions

At session end, extract and persist learnings:

```text
┌─────────────────────────────────────────────────────────────┐
│                    Session Complete                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Extract Episode                                     │
│                                                              │
│  uv run python \                                             │
│    .claude/skills/memory/scripts/extract_session_episode.py \│
│    ".agents/sessions/[session].json"                         │
│                                                              │
│  → Structured episode from session transcript                │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Store Key Memories                                  │
│                                                              │
│  mcp__serena__write_memory(...)                              │
│                                                              │
│  → Persist important patterns for future sessions            │
└─────────────────────────────────────────────────────────────┘
```

### Workflow 3: Failure Analysis

When investigating past failures:

```python
from datetime import datetime, timedelta, UTC

# 1. Find failed sessions
failures = get_episodes(
    outcome="failure",
    since=datetime.now(UTC) - timedelta(days=30),
)

# 2. Analyze each failure
for failure in failures:
    # Decisions in timestamp order. Takes the episode id, not the session id.
    decisions = get_decision_sequence(failure["id"])

    errors = [e for e in failure["events"] if e.get("type") == "error"]
    recoveries = [d for d in decisions if d.get("type") == "recovery"]

    print(f"Session: {failure['session']}")
    print(f"Lessons: {'; '.join(failure['lessons'])}")
```

## Agent-Specific Integration

### Orchestrator Agent

The orchestrator uses memory to route tasks effectively:

```python
# Check for relevant past context
context = search_memory("[task description]", max_results=5)

# Review past similar task outcomes
past_tasks = get_episodes(task="[task keywords]")

# Route to appropriate agent with context
```

### Analyst Agent

The analyst uses episodic memory for investigation:

```python
# Research phase: gather all relevant memories
knowledge = search_memory("[investigation topic]", max_results=20)

# Look for past investigations. The task filter is a case-insensitive
# substring match, so run one query per term.
investigations = [
    episode
    for term in ("investigate", "research", "analyze")
    for episode in get_episodes(task=term)
]

# Build analysis from historical context
```

### Implementer Agent

The implementer reviews past implementation decisions:

```python
# Review past implementation decisions
decisions = [
    decision
    for episode in get_episodes()
    for decision in episode["decisions"]
    if decision.get("type") == "implementation"
]
```

### Retrospective Agent

The retrospective agent captures learnings:

```bash
# Extract session episode
result=$(uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" "[log]")

```

## Session Protocol Integration

### Session Start

At session start, agents SHOULD:

```python
# 1. Read mandatory memory (BLOCKING)
mcp__serena__read_memory(memory_file_name="usage-mandatory")

# 2. Search for relevant project context
search_memory("[session objectives]", max_results=10)

# 3. Review recent episodes
get_episodes(since=datetime.now(UTC) - timedelta(days=7), max_results=5)
```

### Session End

At session end, agents SHOULD:

```bash
# 1. Extract episode from session log
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" "[log]"

# 2. Store cross-session context
mcp__serena__write_memory(memory_file_name="[relevant-memory]", content="...")

# 3. Commit changes
git add .agents/memory/ .serena/memories/
git commit -m "session: Extract episode and update memory"
```

## Best Practices

### For All Agents

1. **Memory First**: Always search memory before multi-step reasoning
2. **Check Patterns**: Review proven patterns before implementation
3. **Avoid Anti-Patterns**: Check failure patterns before risky operations
4. **Record Decisions**: Ensure session logs capture decision rationale
5. **Extract Learnings**: Always extract episodes at session end

### For Memory Queries

1. **Be Specific**: "shell array handling" not "arrays"
2. **Use Filters**: Limit results to avoid information overload
3. **Cache Results**: Reuse within a session to reduce latency

### For Episode Management

1. **Extract Immediately**: Don't delay episode extraction
2. **Verify Outcomes**: Ensure decisions have outcome tracking
3. **Store Lessons**: Make lessons actionable and specific

## Error Handling

### Episode Not Found

```bash
# Check if episode exists, extract if not
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" "[log]"
```

## Performance Considerations

| Operation | Typical Latency | Notes |
|-----------|----------------|-------|
| Skill script invocation | 50-100ms | Python interpreter startup |
| `search_memory` | 300-500ms | File-based search |
| `get_episodes` | 100-200ms | File enumeration |
| Episode extraction | 2-5s | Parsing and analysis |

### Optimization Tips

1. **Cache module imports**: import once per session
2. **Limit `max_results`**: reduce processing overhead, since every matched file is read in full
3. **Batch episode queries**: one `get_episodes` call beats a loop of `get_episode`

## Related Documentation

- [Skill overview](../SKILL.md) - Memory gate skill guide
- [Quick Start](../../memory-search/references/quick-start.md) - Common patterns
- [API Reference](../../memory-search/references/api-reference.md) - Complete function signatures
- [Skill Reference](../../memory-search/references/skill-reference.md) - Skill script documentation
- ADR-007 - Memory-First Architecture
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
