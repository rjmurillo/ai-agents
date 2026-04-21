# Per-Issue Session Handoffs

Structured handoff documents written at session end and read at session start so cross-session work survives context compaction, session crashes, and agent handoffs.

## Scope

This directory holds **per-issue** handoffs. One handoff file per active issue, rewritten each session that touches the issue.

This is **Tier 2-per-issue**, complementing (not replacing) the tiers defined in [ADR-014](../../architecture/ADR-014-distributed-handoff-architecture.md):

| Tier | Location | Scope | When to use |
|------|----------|-------|-------------|
| Session log | `.agents/sessions/YYYY-MM-DD-session-NN.json` | Single session | Always. Canonical session record. |
| **Per-issue handoff** | `.agents/sessions/handoffs/{YYYY-MM-DD}-{NNNN}-handoff.md` | Single issue, across sessions | When an issue spans multiple sessions |
| Per-branch handoff | `.agents/handoffs/{branch}/{session}.md` | Single branch | Multi-session branch coordination (ADR-014 Tier 2) |
| Canonical dashboard | `.agents/HANDOFF.md` | Project-wide, read-only | Read-only reference, 5K hard cap |

**Per-issue vs per-branch**: One branch may cover multiple issues; one issue may survive across branches (rebase, rework). The per-issue handoff keeps continuity anchored to the work unit, not the branch name.

## File Naming

```text
.agents/sessions/handoffs/{YYYY-MM-DD}-{ISSUE_NUMBER}-handoff.md
```

Examples:

- `.agents/sessions/handoffs/2026-04-21-1725-handoff.md`
- `.agents/sessions/handoffs/2026-04-22-1725-handoff.md` (continued next session)

Rules:

1. **One file per session per issue**. Each session creating or advancing an issue writes a dated file.
2. **Date is the session end date** (ISO 8601), not the issue open date.
3. **Issue number only** (no `#` prefix, no leading zeros stripped from 4-digit numbers).
4. **Overwrite rule**: If a handoff for `{date}-{issue}` already exists this session, update it in place.

## Template

Copy from [`../../templates/HANDOFF.md`](../../templates/HANDOFF.md). Fill every section. Empty sections are protocol violations, not an optimization.

## When the Session Protocol Requires a Handoff

- **Session End** (BLOCKING): See [SESSION-PROTOCOL.md § Session End Phase 1.5](../../SESSION-PROTOCOL.md).
  - Agent MUST write the handoff before closing the session when the issue is not `complete`.
  - Agent MAY omit the handoff only when the issue is closed in the same session (merged PR, explicit close).
- **Session Start** (BLOCKING): See [SESSION-PROTOCOL.md § Session Start Phase 2.5](../../SESSION-PROTOCOL.md).
  - Agent MUST read the latest handoff for the issue before modifying files.
  - Agent MUST run the Verification on Resume checklist in the handoff.

## Handoff vs Session Log

Both exist. They answer different questions:

| Question | Source |
|----------|--------|
| What happened in session N? | Session log (`.agents/sessions/*.json`) |
| Where do I resume work on issue #N? | Per-issue handoff (this directory) |

The session log is an immutable audit trail. The handoff is a rolling continuation note. Keep them in sync by linking the handoff to the session log in the `Related` section.

## Lifecycle

1. **Created** on first session-end that leaves the issue incomplete.
2. **Updated** on each subsequent session end for the same issue.
3. **Archived** on issue close: move the final handoff to `.agents/archive/handoffs/{year}/` or delete if the merged PR captures the same context.

Do not delete handoffs while the issue is open. Stale handoffs cause silent state corruption per the failure mode documented in issue #1725.

## Verification

Before treating a handoff as authoritative at session start, run the **Verification on Resume** checklist at the bottom of the handoff file. Claude Code and sibling agents must treat the handoff as a hint until verified against `git status`, file existence, and branch state (Claude Code memory model: memory is a hint, code is ground truth).

## References

- Issue #1725: original proposal
- [ADR-014](../../architecture/ADR-014-distributed-handoff-architecture.md): distributed handoff architecture
- [`../../templates/HANDOFF.md`](../../templates/HANDOFF.md): template
- [`../../SESSION-PROTOCOL.md`](../../SESSION-PROTOCOL.md): protocol gates
