# Token Counting for Memory Files

## Quick Start

```bash
# Count tokens in single file
python3 count_memory_tokens.py .serena/memories/memory-index.md

# Count all memories in directory
python3 count_memory_tokens.py .serena/memories --total

# Recursive with custom pattern
python3 count_memory_tokens.py .serena/memories -r --pattern "*.md" --total

# Force recount (ignore cache)
python3 count_memory_tokens.py .serena/memories -f
```

## Installation

```bash
pip install tiktoken
```

## Caching

Token counts are cached in `.serena/.token-cache.json` for performance:

- Cache invalidated on file modification (SHA-256 hash check)
- Speeds up repeated queries by 10-100×
- Safe to delete cache file (will rebuild on next run)

## Integration with PowerShell

From `Search-Memory.ps1`:

```powershell
# Get token count for memory
$tokenCount = python3 .claude/skills/memory/scripts/count_memory_tokens.py "$memoryPath" |
    Select-String -Pattern '(\d+,?\d*) tokens' |
    ForEach-Object { $_.Matches.Groups[1].Value -replace ',' }

Write-Host "Found memory: $($memory.Name) ($tokenCount tokens)"
```

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
