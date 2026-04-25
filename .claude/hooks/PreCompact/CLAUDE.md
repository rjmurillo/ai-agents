# PreCompact Hooks

Hooks in this directory run before Claude Code compacts the conversation context.

## invoke_compact_checkpoint.py

Snapshots work-in-progress state before context is lost to compaction.

**Captures**: Session log path, open TODO items, current branch, resume context.

**Output**: Resume context string printed to stdout (injected into post-compaction context).

**Exit Codes**: Always 0 (fail-open, never blocks compaction).

**Bypass**: Not applicable (always runs, always succeeds).

## References

- Issue #1703 (lifecycle hook infrastructure)
- ADR-008 (protocol automation via lifecycle hooks)
