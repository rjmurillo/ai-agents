# PreCompact Hooks

Hooks in this directory run before Claude Code compacts the conversation context.

## invoke_compact_checkpoint.py

Snapshots work-in-progress state before context is lost to compaction.

**Captures**: Session log path, open TODO items, current branch, resume context.

**Output**: Resume context string printed to stdout (injected into post-compaction context).

**Exit Codes**: Always 0 (fail-open, never blocks compaction).

**Bypass**:

- Skips with exit 0 when `skip_if_consumer_repo()` returns true (the
  downstream `ai-agents` install bundles this hook but consumer repos that
  vendor the install do not need to checkpoint our internal state).
- On checkpoint write failure (full disk, read-only mount, permission error),
  logs a `[WARNING]` to stderr and continues. Resume context is still printed
  to stdout for the post-compaction session.
- On any unhandled exception, logs a `[WARNING]` to stderr and exits 0
  (fail-open; never blocks compaction).

## References

- Issue #1703 (lifecycle hook infrastructure)
- ADR-008 (protocol automation via lifecycle hooks)
