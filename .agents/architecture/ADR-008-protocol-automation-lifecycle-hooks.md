---
id: ADR-008
status: accepted
date: 2026-08-19
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-008: Protocol Automation via Lifecycle Hooks

## Status

Accepted

## Date

2025-12-20

## Context

The ai-agents system relies on SESSION-PROTOCOL.md for consistency, but compliance depends on agent discipline:

1. **Manual enforcement**: Agents must remember to create session logs, read HANDOFF.md, etc.
2. **Protocol drift**: Under time pressure, agents skip steps
3. **Inconsistent artifacts**: Some sessions have complete logs, others have none
4. **No verification**: No automated check that protocol was followed

Research into [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) revealed comprehensive lifecycle hooks:

- Pre/post task hooks for validation and cleanup
- Session start/end hooks for context management
- File modification hooks for format enforcement
- Auto-save middleware with 30-second intervals

These hooks achieve 10-20x faster batch agent spawning by automating setup that would otherwise be manual.

## Decision

**Lifecycle hooks MUST automate SESSION-PROTOCOL enforcement.**

Specifically:

1. **Pre-session hook**: Auto-create session log, verify HANDOFF.md exists
2. **Post-session hook**: Run markdown lint, update HANDOFF.md, commit artifacts
3. **Pre-commit hook**: Validate session log format, check for uncommitted memories
4. **File modification hooks**: Enforce consistent formatting on save

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Manual discipline | No tooling required | Unreliable, drift | Current pain point |
| CI-only validation | Catches issues eventually | Too late, no prevention | Feedback loop too slow |
| Lifecycle hooks | Prevents issues, automates | Implementation effort | **Chosen** |

### Trade-offs

- **Complexity**: Hook system adds moving parts
- **Flexibility reduction**: Hooks enforce patterns even when deviation might be appropriate
- **Debugging difficulty**: Automated actions harder to trace than manual ones

## Consequences

### Positive

- Protocol compliance becomes automatic, not aspirational
- Consistent artifact structure across all sessions
- Reduced cognitive load - agents focus on task, not bookkeeping
- Session checkpointing enables pause/resume (Issue #174)

### Negative

- Hook failures can block work
- Over-automation may mask understanding gaps
- Configuration complexity for hook customization

### Neutral

- Shifts protocol enforcement from runtime to configuration

## Implementation Notes

### Hook Types (from claude-flow research)

| Hook | Trigger | Action |
|------|---------|--------|
| `session.start` | Session begins | Create log, retrieve context |
| `session.end` | Session closes | Update HANDOFF, lint, commit |
| `task.pre` | Before task execution | Validate prerequisites |
| `task.post` | After task completion | Store learnings |
| `file.modify` | File saved | Format validation |
| `commit.pre` | Before git commit | Lint, artifact check |

### Phase 5A Implementation Order

1. Session start/end hooks (highest value)
2. Commit hooks (prevent broken artifacts)
3. Task hooks (advanced automation)

## Related Decisions

- ADR-007: Memory-First Architecture (hooks enforce retrieval)
- ADR-004: Pre-Commit Hook Architecture (existing foundation)
- SESSION-PROTOCOL.md (defines what hooks enforce)

## Failure Semantics

All hooks follow ADR-042 (Python-first). Failure semantics are scoped:

- **Amended 2026-06-11 per ADR-071 item 5 and ADR-066.** This ADR previously stated that runtime and I/O errors during hook execution are fail-open (the hook logs and returns success so agent work proceeds). That position is replaced: ADR-071 (Accepted) Decision item 5 records the binding rule that hooks MUST fail closed and loud, never silently degrade, and ADR-066 (hook fail-open reconciliation) is the detailed D1/D2 reconciliation of prior guidance to that rule. The default for hooks is prevention-first, fail-closed-and-loud: runtime errors that escape prevention exit non-zero with actionable stderr, and silent exit 0 as a recovery path violates ADR-071 item 5 and ADR-066 D1. See `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` (binding, Accepted) and `.agents/architecture/ADR-066-hook-fail-open-reconciliation.md` (failure-mode policy detail, exit-code table, and the #2205 incident rationale).
- **`invoke_false_completion_gate` was a policy gate (retired by #3184).** When an agent claimed completion without test evidence, the gate exited non-zero (exit code 2) by design to block the false claim. Under ADR-066 that was not an exception; it was an instance of the default. The hook itself is gone (see the Implementation Status table), so the bullet records the reasoning, not a live gate.
- **Configuration and bootstrap failures terminate non-zero.** The standard hook import boilerplate exits with code 2 when the plugin lib directory is missing (per ADR-047 plugin lib resolution and ADR-035 exit-code conventions). Stop runs on a host that ignores non-zero exits; per ADR-066 D2 the repository still treats a failed Stop hook as failed and relies on pre-push, CI, and runtime-contract tests to catch the broken artifact before release.

## References

- Epic #183: Claude-Flow Inspired Enhancements
- Issue #170: Lifecycle Hooks
- Issue #174: Session Checkpointing
- [claude-flow hooks architecture](https://github.com/ruvnet/claude-flow)
- `.agents/analysis/claude-flow-architecture-analysis.md`

## Implementation Status

This is the one status table in this ADR. It previously appeared twice, once
above the References section and once here, with different columns and no
statement of which was current. A reader could not tell which to trust and an
editor could not tell which to update, which is part of why three retirements
went unrecorded here. The upper section now holds only the failure-semantics
amendment, which is the material that was unique to it.

Implemented via Issue #1703. Status reflects the tree, not the 2026 decision:
this ADR records what was decided, so a hook that has since been retired keeps
its row and gains a retirement note rather than disappearing.

| Hook | File | Type | Status |
|------|------|------|--------|
| **SessionStart: Context Loader** | `SessionStart/invoke_context_loader.py` | SessionStart | Implemented, narrowed by #5170 |
| **PreCompact: Compact Checkpoint** | `PreCompact/invoke_compact_checkpoint.py` | PreCompact | Implemented, trimmed by #3273 |
| **PreToolUse: False Completion Gate** | `PreToolUse/invoke_false_completion_gate.py` | PreToolUse | Retired by #3184 |
| **PostToolUse: Plan State Sync** | `PostToolUse/invoke_plan_state_sync.py` | PostToolUse | Retired by #3184 |
| **Stop: Auto-Retrospective** | `Stop/invoke_auto_retrospective.py` | Stop | Retired by #3349 |

### Amendment 2026-07-26 (Issue #3373)

Three of the five hooks this ADR introduced have been retired, across two
purges. Until this amendment all five were still marked implemented, so the
document answered "what is the lifecycle-hook surface" with files that are not
on disk.

| Hook | Retired by | Reason of record |
|------|-----------|------------------|
| `invoke_false_completion_gate.py` | #3184 | Retired for hook ROI reduction; the claim it gated is covered by CI test evidence |
| `invoke_plan_state_sync.py` | #3184 | Retired under the same program; the state it checkpointed had no reader |
| `invoke_auto_retrospective.py` | #3349 | Retired under the same program; retrospectives are authored, not generated |

A fourth hook, `invoke_test_auto_approval.py`, was retired by #3295. It is
named in the prose below but was never one of the five this ADR introduced, so
it is not counted above.

The two survivors are recorded in `AUTHORIZED_HOOKS` in
`tests/hooks/test_dispatch_groups_parity.py`, which is the live ledger of what
runs. This table is the historical record of what was decided; that ledger is
the record of what executes. Consult the ledger when the question is "what runs
today".

`tests/hooks/test_adr_hook_claims.py` now fails when any ADR marks a hook
implemented whose file is absent. Two prior purges left this section stale in
silence; a third correction with no gate buys one clean read and nothing else.

### Amendment 2026-08-19 (Issue #5168, PR #5170)

The Context Loader hook narrowed: it no longer auto-injects `.agents/HANDOFF.md`
into session context. That file had carried a "read-only, as of 2025-12-22"
banner unchanged for eight months, listing pull requests long since resolved;
ADR-014 already superseded it with per-issue handoffs and Serena memory, and
the mandatory session-log protocol this hook originally served was itself
retired as negative-ROI in PR #5135. Injecting the stale file cost roughly
1,000 tokens per session for no compensating value. The hook still auto-injects
the latest retrospective and the pending-retro-skeleton reminder; the
criterion this ADR records ("SessionStart loads context") remains met, on a
narrower path.

### Acceptance Criteria Mapping

As accepted 2025-12-20. Rows for retired hooks are kept because they record
what the decision claimed at the time; the criterion is no longer met by a
hook.

| Criteria | Hook | Evidence | Still met by a hook |
|----------|------|----------|---------------------|
| SessionStart loads context | Context Loader | Auto-injects HANDOFF.md + latest retro | Partially, HANDOFF.md dropped by #5168/#5170 |
| Hook execution logged | All hooks | Audit trail in `.agents/.hook-state/` | Yes, for the survivors |
| Zero context reading failures | Context Loader | Eliminates manual context loading requirement | Yes |
| PreToolUse blocks false completion | False Completion Gate | Blocks commit/PR without test evidence | No, retired by #3184 |
| Stop generates retros | Auto-Retrospective | Creates `.agents/retrospective/{date}-auto-retro.md` | No, retired by #3349 |

### Design Principles

- **Fail-closed-and-loud (amended 2026-06-11 per ADR-066)**: hooks exit non-zero with actionable stderr on failures; the original "non-blocking hooks always exit 0" principle is superseded
- **Typed memory lanes**: Each hook writes to its own state (per hilyfux feedback on #1703)
- **Idempotent**: Stop retro skips if one already exists for today. Retired with the Stop hook in #3349; kept here as part of the accepted decision.
- **Bypass-friendly**: Environment variables for all gates. The two named at acceptance, `SKIP_COMPLETION_GATE` and `SKIP_AUTO_RETRO`, went with their hooks in #3184 and #3349 and are no longer read anywhere.

---

*Template Version: 1.0*
*Origin: Epic #183 closing comment (2025-12-20)*
