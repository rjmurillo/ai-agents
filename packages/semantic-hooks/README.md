# semantic-hooks

Semantic tension tracking hooks for Claude Code CLI. Implements ΔS (semantic tension) measurement, knowledge boundary detection, and reasoning trace logging.

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

3. **SessionStart** - Loads previous context from memory

4. **PreCompact** - Checkpoints semantic tree before context compaction

5. **SessionEnd** - Persists session summary

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
