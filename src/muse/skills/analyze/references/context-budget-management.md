---
source: wiki/concepts/AI Productivity/Context Budget Management for AI Agents.md
created: 2026-04-11
review-by: 2026-07-11
---

# Context Budget Management

Raw tool output floods context windows. After 30 minutes of agentic work, 40% of context budget gone, triggering compaction and amnesia.

## Three Problems

| Problem | Mechanism | Reduction |
|---------|-----------|-----------|
| Raw data flood | Store in SQLite, return reference handle, query via BM25 | 98% |
| Compaction amnesia | Index edits/tasks/errors in FTS5, reinject on compaction | Session continuity |
| LLM as data processor | Generate code that processes data, not read-then-analyze | O(1) vs O(n) context |

## Think in Code Principle

The LLM should be a code generator, not a data processor. Reading files serially into context burns tokens quadratically.

- **Wrong**: Read file 1, analyze, read file 2, analyze (O(n) context, serial)
- **Right**: Write script that reads all files and outputs only the answer (O(1) context, parallel)

## Hook Architecture

| Hook | When | Purpose |
|------|------|---------|
| SessionStart | Session begins | Inject routing instructions |
| PreToolUse | Before large-output tools | Redirect to sandbox equivalent |
| PostToolUse | After any tool | Record event to index |
| PreCompact | Before compaction | Save state, trigger BM25 retrieval on resume |

## Diagnostic Signals

| Signal | Indicates |
|--------|-----------|
| Agent forgets mid-task state | Missing compaction recovery mechanism |
| Context fills in < 30 min | Raw tool output not sandboxed |
| Repeated file reads | No indexing or caching layer |
| Agent summarizes data inline | Should generate processing code instead |
