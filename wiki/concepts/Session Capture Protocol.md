# Session Capture Protocol

The Session Capture Protocol defines what an orchestrator records in the session log's `workLog` and `nextSteps` fields to make sessions recoverable and auditable. The goal is to distinguish **behavioral signal** (information that affects future decisions) from **background noise** (routine operations already captured in transcripts).

## What to Capture (Behavioral)

| Category | Description | Example |
|---|---|---|
| **Decisions made** | Architecture choices, approach pivots, agent routing rationale | "Chose sequential over parallel routing because analyst output was needed before architect could proceed" |
| **Blockers hit** | What stopped progress, workarounds attempted, escalations needed | "QA agent timed out; routed to critic as fallback per graceful-degradation principle" |
| **State changes** | Files modified, branches created, issues filed, PRs opened | "Created `.agents/analysis/003-session-protocol-skill-gate.md`; filed issue #1692" |
| **Open questions** | Unresolved ambiguities requiring human input or a follow-up session | "Unclear whether eval methodology (#1688) must land before this change can be validated" |
| **Next steps** | Concrete continuation plan with enough context for a cold-start | "Session 2: add cross-reference from SESSION-PROTOCOL.md Phase 1 doc-update step" |

## What to Skip

- **Tool invocations** — already in transcript logs
- **Background research** that did not change the plan
- **Routine operations** — file reads, status checks, lint runs
- **Intermediate agent responses** that were superseded by synthesis

## Decision Rule

> If removing this entry would leave the next session unable to reproduce a decision or continue the work, **keep it**. Otherwise, **skip it**.

## Example: Good vs Bad `workLog` Entries

### ✅ Good Capture (behavioral signal)

```json
{
  "workLog": [
    {
      "action": "Decided to use graph traversal over flat iteration for memory relationships",
      "result": "Memory relationships form cycles; flat iteration would miss connected memories",
      "files": ["memory_enhancement/graph.py"]
    },
    {
      "action": "Hit blocker: existing schema lacks 'importance' field",
      "result": "Added optional 'importance' to schema with backward-compatible migration path",
      "files": ["memory_enhancement/schema.py", ".agents/schemas/memory.schema.json"]
    }
  ],
  "nextSteps": [
    "Validate health report output against real memories",
    "Add CLI entry point for health command"
  ]
}
```

### ❌ Bad Capture (background noise)

```json
{
  "workLog": [
    {
      "action": "Read file memory_enhancement/graph.py",
      "result": "File contents loaded"
    },
    {
      "action": "Ran git status",
      "result": "3 files modified"
    }
  ],
  "nextSteps": []
}
```

### ❌ Worst Case (empty)

```json
{
  "workLog": [],
  "nextSteps": []
}
```

Sessions ending with empty `workLog` have failed to capture behavioral context. At minimum, capture: (1) what was the session objective, (2) what was achieved, (3) what blocked or delayed progress, (4) what should the next session know.

## Cross-References

- [Session Gate (Blocking)](../../templates/agents/orchestrator.shared.md) — orchestrator checklist that triggers this protocol
- [SESSION-PROTOCOL.md Phase 1: Documentation Update](../../.agents/SESSION-PROTOCOL.md) — canonical session end requirements
