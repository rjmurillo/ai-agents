# PreCompact Hook

## Purpose

Checkpoints work-in-progress state before context compaction occurs, enabling
seamless session resumption after context is compressed.

## Hooks

### invoke_compact_checkpoint.py

- **Type**: PreCompact (non-blocking)
- **Exit Codes**: Always 0 (fail-open)
- **Bypass**: N/A (always runs, always succeeds)

### Behavior

1. Captures current branch, session log path, and open work items
2. Writes checkpoint to `.agents/.hook-state/pre-compact-{date}-{time}.json`
3. Prints resume context string to stdout (injected into compacted context)

### Output (stdout)

A single-line resume context string, e.g.:

```text
Compaction occurred at 14:32:15. Branch: feature/1703-hooks. Session: 2026-04-20-session-01.json. Open items: 3
```
