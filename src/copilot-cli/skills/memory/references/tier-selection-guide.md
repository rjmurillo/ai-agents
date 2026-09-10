# Tier Selection Guide

Deep guidance for selecting the correct memory tier.

## Tier Characteristics

| Tier | Access Speed | Scope | Reliability | Content Type |
|------|--------------|-------|-------------|--------------|
| **0: Working** | Instant | Current session | 100% | Active context |
| **1: Semantic** | ~500ms | All projects | 100% (Serena) | Facts, patterns, rules |
| **2: Episodic** | ~100ms | This project | 100% (local) | Session history, decisions |

## Selection by Question Type

### "What is X?" → Tier 1

Factual questions about concepts, patterns, or rules.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "shell array handling"
```

### "What happened when...?" → Tier 2

Historical questions about past sessions.

```python
get_episode("2026-01-01-session-126")
get_episodes(outcome="failure", since=datetime.now(UTC) - timedelta(days=7))
```

### "Why did X lead to Y?" → Tier 2

Read the episodes that recorded the decision and its outcome.

```python
get_episodes(outcome="failure", max_results=20)
```

### "What should I try?" → Multi-Tier

Complex questions requiring synthesis.

```text
1. Tier 1: Search for relevant patterns
2. Tier 2: Check if a similar situation occurred before, and how it ended
3. Synthesize recommendation
```

## Selection by Task Phase

| Task Phase | Primary Tier | Secondary Tier |
|------------|--------------|----------------|
| **Starting work** | 1 (context) | 2 (similar sessions) |
| **Encountering error** | 1 (solutions) | 2 (prior occurrences) |
| **Making decision** | 1 (constraints) | 2 (prior outcomes) |
| **Completing session** | 2 (extract) | 1 (record the fact) |
| **Debugging issue** | 2 (timeline) | 1 (known causes) |

## Fallback Strategy

```text
Primary tier unavailable?
│
├── Tier 2 unavailable
│   └── Check .agents/memory/episodes/ exists
│   └── If missing, no historical data yet
```

## Common Mistakes

### Mistake: Using Tier 1 for session history

**Wrong**: `search_memory("what did I do yesterday")`
**Right**: `get_episodes(since=datetime.now(UTC) - timedelta(days=1))`

### Mistake: Using Tier 2 for fact lookup

**Wrong**: Scanning episodes for API documentation
**Right**: `search_memory("API authentication")`

## Multi-Tier Query Example

When answering "How should I handle authentication errors?":

```python
import os
import sys
from datetime import datetime, timedelta, UTC

_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".claude"
sys.path.insert(0, f"{_root}/skills/memory")
from memory_core.memory_router import search_memory
from memory_core.reflexion_memory import get_episode, get_episodes

# Tier 1: documented patterns
facts = search_memory("authentication error handling")

# Tier 2: relevant past sessions and how they ended
episodes = get_episodes(task="authentication", max_results=10)

# Synthesize the answer from both tiers
```
