# Session State  -  Issue #{issue-number}

> **Purpose**: Durable, agent-updated checkpoint that survives compaction and crashes. Written by the active agent while work is in flight; read by the next session (or the orchestrator on handoff) to resume without restarting.
> **Location**: `.agents/sessions/state/{issue-number}.md`
> **Related**: `.agents/SESSION-PROTOCOL.md`, `.agents/HANDOFF.md`, issue #1728 (context pressure detection)

## Header

- **Issue**: #{issue-number}  -  {short-title}
- **Branch**: {branch-name}
- **Started**: {YYYY-MM-DD HH:MM TZ}
- **Last Update**: {YYYY-MM-DD HH:MM TZ}
- **Owner Agent**: {orchestrator | implementer | analyst | ...}

## Progress

- **Current Step**: {N} of {total}
- **Step Description**: {what this step does}
- **Files Modified**: {comma-separated list, relative paths}
- **Files Pending**: {files identified but not yet changed}
- **Tests Status**: {not-yet-run | passing | failing | n/a}
- **Commits on Branch**: {count; reference last commit SHA}

## Context Pressure

- **Level**: LOW | MEDIUM | HIGH | CRITICAL
- **Signal(s) Observed**: {none | placeholder code | skipped step | repeated work | lost-track-of-files | other}
- **Estimated Remaining Budget**: {tokens or qualitative: ample / tight / exhausted}

Thresholds (guidance, not enforcement):

| Level | Budget Consumed | Required Action |
|-------|----------------|-----------------|
| LOW | <50% | Continue; update this file at major-step boundaries |
| MEDIUM | 50-70% | Commit current work before the next complex operation |
| HIGH | 70-90% | Commit, update this file, write `.agents/HANDOFF.md`, return `CONTEXT_PRESSURE: HIGH` to orchestrator |
| CRITICAL | >90% | Stop. Commit. Handoff. End session cleanly. Do not start new multi-file changes. |

## Decisions Made

- {decision 1: what, why, alternatives considered}
- {decision 2: ...}

## Remaining Work

1. {atomic next step}
2. {atomic next step}
3. {...}

Each item SHOULD be small enough to complete and commit as a single unit. If an item looks too large, split it before resuming.

## Handoff Notes

- **Where the next agent should start**: {file:line or step number}
- **What NOT to redo**: {already-completed steps the next agent should trust}
- **Open questions**: {unresolved decisions requiring human or specialist input}
- **Blockers**: {external dependencies, failing tests the next agent must address first}

## Signal to Orchestrator

When this agent returns control, it SHOULD emit a single structured line:

```
CONTEXT_PRESSURE: {LOW|MEDIUM|HIGH|CRITICAL}  -  checkpointed at step {N}/{total}, {remaining} steps left, files: {count} modified
```

The orchestrator uses this signal to decide whether to dispatch a fresh sub-session or continue in the same context window.
