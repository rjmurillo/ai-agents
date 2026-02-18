# semantic-hooks

Semantic tension tracking hooks for Claude Code CLI. Implements ΔS (semantic tension) measurement, knowledge boundary detection, stuck loop detection, and reasoning trace logging.

## Installation

```bash
# From ai-agents repo
cd packages/semantic-hooks
pip install -e .

# Install hooks to Claude Code
semantic-hooks install --claude
```

## What It Does

1. **PreToolUse** - Measures semantic tension (ΔS) before tool execution
   - Warns when entering unfamiliar territory
   - Optionally blocks in "danger zone" (ΔS > 0.85)
   - Suggests bridge topics when available

2. **PostToolUse** - Records semantic nodes after execution
   - Tracks reasoning direction (convergent/divergent/recursive)
   - Builds searchable semantic tree

3. **PostResponse** - Detects stuck loops
   - Uses Jaccard similarity on topic signatures
   - Injects self-reflection nudges when stuck
   - Breaks repetitive topic patterns

4. **SessionStart** - Loads previous context from memory

5. **PreCompact** - Checkpoints semantic tree before context compaction

6. **SessionEnd** - Persists session summary

## Stuck Detection

The stuck detection guard identifies when the agent is repeating similar topics and injects a nudge to break the loop.

### How It Works

1. **Topic Signature Extraction**: Extracts the top 5 significant words from each response, filtering out stop words
2. **Jaccard Similarity**: Compares signatures between consecutive turns
3. **Loop Detection**: Triggers when 3+ consecutive turns have >60% similarity
4. **Nudge Injection**: Injects a self-reflection prompt to break the pattern

### Configuration

```yaml
# ~/.semantic-hooks/config.yaml

stuck_detection:
  history_path: ~/.semantic-hooks/stuck-history.json
  max_history: 10
  stuck_threshold: 3          # Consecutive similar turns to trigger
  similarity_threshold: 0.6   # Jaccard similarity threshold
  min_significant_words: 2
  user_name: Richard          # Name used in nudge prompts
```

### Programmatic Usage

```python
from semantic_hooks.guards import (
    StuckDetectionGuard,
    StuckConfig,
    check_stuck,
    extract_topic_signature,
    jaccard_similarity,
    reset_stuck_history,
)
from pathlib import Path

# Quick check
result = check_stuck(
    "Your response text here...",
    Path("~/.semantic-hooks/stuck-history.json").expanduser()
)
if result.stuck:
    print(result.nudge)

# Full guard usage
config = StuckConfig(
    stuck_threshold=3,
    similarity_threshold=0.6,
    user_name="Richard"
)
guard = StuckDetectionGuard(config=config)

# Check a response
from semantic_hooks.core import HookContext, HookEvent
context = HookContext(
    event=HookEvent.POST_TOOL_USE,
    tool_result="Your response text..."
)
result = guard.check(context)

# Reset history after successful topic change
guard.reset()
```

## Configuration

```yaml
# ~/.semantic-hooks/config.yaml

embedding:
  provider: openai
  model: text-embedding-3-small

thresholds:
  safe: 0.4
  transitional: 0.6
  risk: 0.85

guard:
  block_in_danger: false  # Set true to block high-risk operations
  inject_bridge_context: true
  trajectory_window: 5

stuck_detection:
  stuck_threshold: 3
  similarity_threshold: 0.6
  user_name: User
```

## CLI Commands

```bash
# Status
semantic-hooks status

# View semantic tree
semantic-hooks tree
semantic-hooks tree --export session.json

# Configuration
semantic-hooks config --show
semantic-hooks config --delta-s-threshold 0.7
semantic-hooks config --block-in-danger true

# Uninstall
semantic-hooks uninstall --claude
semantic-hooks uninstall --claude --purge  # Also removes memory
```

## Semantic Zones

| Zone | ΔS Range | Meaning |
|------|----------|---------|
| 🟢 Safe | < 0.4 | Well-known territory |
| 🟡 Transitional | 0.4 - 0.6 | Moving between concepts |
| 🟠 Risk | 0.6 - 0.85 | Approaching unknown territory |
| 🔴 Danger | > 0.85 | High hallucination risk |

## Data Storage

- Config: `~/.semantic-hooks/config.yaml`
- Memory: `~/.semantic-hooks/memory.db`
- Logs: `~/.semantic-hooks/hooks.log`
- Sessions: `~/.semantic-hooks/sessions/`
- Checkpoints: `~/.semantic-hooks/checkpoints/`

## Serena Integration

When Serena memory is available, semantic-hooks can import context:

```python
from semantic_hooks.memory import SemanticMemory

memory = SemanticMemory(serena_path="~/.serena/memory.json")
memory.import_from_serena()
```

## License

MIT
