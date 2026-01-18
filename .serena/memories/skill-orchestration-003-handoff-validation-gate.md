# Skill-Orchestration-003: Handoff Validation Gate

## Statement

Orchestrator MUST validate Session End checklist before accepting agent handoff; require validation evidence

## Context

Before orchestrator accepts handoff from specialized agent (implementer, analyst, etc.), verify Session End protocol compliance

## Evidence

**Mass failure (2025-12-20)**: 23 of 24 agents handed off to orchestrator without Session End checklist complete

**No validation step**: Agents closed sessions immediately after work done with no verification pause

**Compliance disparity**: Session Start (79% via blocking gates) vs Session End (4% via trust)

## Metrics

- **Atomicity**: 92%
- **Impact**: 10/10
- **Category**: orchestration, validation, protocol
- **Created**: 2025-12-20
- **Tag**: CRITICAL
- **Validated**: 1 (24-session analysis)

## Pattern

### Orchestrator Handoff Acceptance Criteria

Before accepting agent handoff, orchestrator MUST verify:

1. Session log exists at expected path `.agents/sessions/YYYY-MM-DD-session-NN.md`
2. `Validate-SessionEnd.ps1` passes on session log (exit code 0)
3. Agent provides validation evidence in handoff output

### Rejection Response

If validation fails:

```markdown
❌ **Handoff Rejected**: Session End checklist incomplete

**Session log**: `.agents/sessions/2025-12-20-session-47.md`
**Validation**: FAIL - 3 unchecked requirements
  - [ ] HANDOFF.md update
  - [ ] Markdown lint
  - [ ] Commit changes

**Required action**: Complete Session End checklist before handoff.
Return to session, mark all [x] checkboxes, then re-handoff.
```

### Acceptance Response

If validation passes:

```markdown
✅ **Handoff Accepted**: Session End protocol compliant

**Session log**: `.agents/sessions/2025-12-20-session-44.md`
**Validation**: PASS - All requirements complete
**Commit SHA**: 3b6559d

Proceeding with orchestrator workflow.
```

## Implementation

**In orchestrator agent prompt:**

```markdown
### Agent Handoff Validation

When agent signals session complete and hands off:

1. Determine session log path from agent context
2. Invoke: `pwsh -File scripts/Validate-SessionEnd.ps1 -SessionLogPath [path]`
3. Check exit code:
   - Exit 0 → Accept handoff, proceed
   - Exit 1 → Reject handoff, return to agent with error details

DO NOT accept handoff from agent without validation evidence.

**Verification**: Validation script output appears in orchestrator transcript.
```

## Verification

**Test orchestrator validation:**

```markdown
# Scenario: Agent completes work, attempts handoff
Agent: "Work complete, handing off to orchestrator"

# Orchestrator validation check
Orchestrator:
  1. Read session log at .agents/sessions/2025-12-20-session-47.md
  2. Run Validate-SessionEnd.ps1
  3. If PASS: Accept handoff
     If FAIL: Reject with specific requirements missing
```

## Related Skills

- Skill-Git-001 (Pre-Commit Validation)
- Skill-Protocol-002 (Verification-Based Gate Effectiveness)
- Skill-Orchestration-002 (Parallel HANDOFF Coordination)

## Source

`.agents/retrospective/2025-12-20-session-protocol-mass-failure.md` (Learning 4, lines 699-717)
