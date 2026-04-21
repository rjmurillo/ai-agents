# Session Capture Protocol

## Purpose

The Session Capture Protocol defines what an orchestrator records in the
session log to make sessions recoverable, auditable, and useful for cold-start
continuation. It distinguishes signal (decisions, blockers, state changes,
open questions, next steps) from noise (tool invocations, routine reads,
background research that did not change the plan).

The protocol applies to the `workLog`, `decisions`, and `nextSteps` fields of
the session log JSON written under `.agents/sessions/YYYY-MM-DD-session-NN.json`.
It is invoked from the `## Session Gate (Blocking)` section of the orchestrator
agent prompt and from `.agents/SESSION-PROTOCOL.md` Phase 1 documentation
update.

> **Location**: This file lives in `.serena/memories/session/` because Serena
> memories are the project's concept store. The `wiki/concepts/` path referenced
> in earlier issues has been superseded.

## What to Capture (Behavioral, Not Background)

| Category | Description | Example |
|----------|-------------|---------|
| **Decisions made** | Architecture choices, approach changes, agent routing changes that altered the plan | "Routed to analyst before architect because the requirement was ambiguous; analyst clarification was needed before architect could proceed" |
| **Blockers hit** | What stopped progress, workarounds attempted, escalations needed | "QA agent timed out; routed to critic as fallback per graceful-degradation principle" |
| **State changes** | Files modified, branches created, issues filed, PRs opened | "Created `.serena/memories/session/session-capture-protocol.md`; updated 5 orchestrator files; filed issue #1692" |
| **Open questions** | Unresolved ambiguities requiring human input or a follow-up session | "Unclear whether eval methodology (#1688) must land before this change can be validated" |
| **Next steps** | Concrete continuation plan with enough context for a cold-start | "Session 2: add cross-reference from SESSION-PROTOCOL.md Phase 1 doc-update step" |

Each entry should be one or two sentences. Lead with the action or decision,
then the result or rationale. A future agent reading the log should be able to
reconstruct *why* a choice was made, not just *what* happened.

## What to Skip

The session log is not a tool transcript. Do not record:

- Tool invocations (already in transcript logs and event streams)
- Background research that did not change the plan
- Routine operations: file reads, status checks, lint runs, directory listings
- Intermediate agent responses that were superseded or rejected
- Speculative paths that were considered and dropped without changing the plan

If a research step *did* change the plan, capture the changed decision under
**Decisions made**, not the research itself.

## Good vs Bad Capture Examples

### Good `workLog` entry

```json
{
  "action": "Selected issue #1692 (P1) from candidates JSON; verified branch matches and no prior PR exists",
  "result": "Cleared to proceed; recorded that #1688 is listed as a soft blocker and decided to proceed (see decisions[2])"
}
```

This entry records a decision (issue selection and proceed-despite-soft-blocker)
and links to a structured decision entry. A future session can reconstruct the
state.

### Bad `workLog` entry

```json
{
  "action": "Ran git status",
  "result": "Working tree clean"
}
```

This entry records a routine tool call with no decision content. It belongs in
the transcript, not the session log. Skip it.

### Good `decisions` entry

```json
{
  "decision": "Treat templates/agents/orchestrator.shared.md as the canonical source and apply the identical sub-section to the 4 platform-specific files",
  "rationale": "Existing structure already shows verbatim duplication; keeping the four platform files in sync prevents drift between deployed surfaces"
}
```

The decision is concrete, the rationale explains *why*, and a reader can
evaluate whether the reasoning still holds.

### Bad `decisions` entry

```json
{
  "decision": "Used the right approach",
  "rationale": "It seemed best"
}
```

Vague decision, vague rationale, no information for a future agent.

## Cross-References

- `templates/agents/orchestrator.shared.md` — Session Gate (Blocking) section
  embeds the protocol inline; this file provides full examples.
- `.agents/SESSION-PROTOCOL.md` — Phase 1: Documentation Update references
  this protocol when defining what session-log content is required.
- `.agents/schemas/session-log.schema.json` — Defines the `workLog`,
  `decisions`, and `nextSteps` fields this protocol targets.

## Why This Exists

PRs #1680 and #1676 enforced that a session-end gate must exist, but did not
specify *what to capture*. Without behavioral guidance, session logs drift
toward either bare checklists (no information) or transcript dumps (too much
noise to be useful for handoff). This protocol fixes that gap by giving
orchestrators an explicit signal-vs-noise filter at session-end time.
