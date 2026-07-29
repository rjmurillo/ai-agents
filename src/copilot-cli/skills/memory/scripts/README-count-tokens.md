# Token Counting for Memory Files

## Quick Start

```bash
# Count tokens in single file
uv run python count_memory_tokens.py .serena/memories/memory-index.md

# Count all memories in directory
uv run python count_memory_tokens.py .serena/memories --total

# Recursive with custom pattern
uv run python count_memory_tokens.py .serena/memories -r --pattern "*.md" --total

# Force recount (ignore cache)
uv run python count_memory_tokens.py .serena/memories -f
```

## Installation

`tiktoken` is already a project dependency (`pyproject.toml`), so `uv sync`
covers it. Install it standalone only when running outside the project venv:

```bash
uv sync          # inside the repo
uv pip install tiktoken   # standalone
```

## Caching

Token counts are cached in `.serena/.token-cache.json` for performance:

- Cache invalidated on file modification (SHA-256 hash check)
- Speeds up repeated queries by 10-100×
- Safe to delete cache file (will rebuild on next run)

## Integration with the Memory Router

Import the counter directly rather than parsing CLI output:

```python
import os
import sys
from pathlib import Path

_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".claude"
sys.path.insert(0, f"{_root}/skills/memory")
sys.path.insert(0, f"{_root}/skills/memory/scripts")

from count_memory_tokens import get_memory_token_count
from memory_core.memory_router import search_memory

for memory in search_memory("context engineering", max_results=5):
    if memory.path:
        tokens = get_memory_token_count(Path(memory.path))
        print(f"Found memory: {memory.name} ({tokens} tokens)")
```

`search_memory.py --format table` already prints a `Tokens` column and a
cumulative budget line, so prefer the CLI when you only need the display.

## Output Format

```text
# Single file
.serena/memories/memory-index.md: 1,234 tokens

# Directory
.serena/memories/memory-token-efficiency.md: 861 tokens
.serena/memories/memory-index.md: 1,234 tokens
.serena/memories/context-engineering-principles.md: 543 tokens

Total: 2,638 tokens across 3 files
```

## Performance

| Operation | Time (cold) | Time (cached) |
|-----------|-------------|---------------|
| Single file | ~100ms | ~5ms |
| 100 files | ~5s | ~200ms |
| 1000 files | ~45s | ~2s |

## Context Engineering Principle

Token cost visibility enables informed ROI decisions:

> "Display token counts for each item so agents can decide whether expensive retrieval is worth the cost."

See: [Context Engineering Analysis](/.agents/analysis/context-engineering.md)

<!-- vendor-portability: declared. This README links .agents/analysis/context-engineering.md as background. It is a documentation citation; the count-tokens script runs without it and a vendored install loses only the link. Issue #2050. -->
