# Serena Memory Subdirectory Convention

## Summary

As of 2026-02-14, Serena memories are organized into topic subdirectories under `.serena/memories/`.

## Key Behavior

- `list_memories` returns ONLY top-level files (indexes)
- `read_memory("subdir/name")` reads files from subdirectories
- `write_memory("subdir/name", content)` writes to subdirectories

## Convention

- **Index files** (`*-index.md`, `README.md`, `usage-mandatory.md`): top level
- **Atomic memories**: in topic subdirectory matching their domain
- **Index references**: use `subdir/memory-name` format

## Token Impact

Reduced `list_memories` output from 829 entries (~5,000 tokens) to 45 entries (~300 tokens). Savings: ~4,700 tokens per session.

## Related

- README.md (top-level) for full directory structure documentation
- Migration script: `scripts/restructure_memories.py`
