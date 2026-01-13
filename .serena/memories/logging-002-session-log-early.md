# Skill-Logging-002: Create Session Log Early

**Statement**: Create session log with checklist template before any work

**Context**: Session start, after reading HANDOFF.md

**Trigger**: Immediately after Phase 2 (Context Retrieval) completion

**Action**: Create `.agents/sessions/YYYY-MM-DD-session-NN.json` with Protocol Compliance checklist

**Evidence**: Session log file exists with checkboxes for each phase

**Anti-pattern**: Starting work without session log

**Atomicity**: 98%

**Tag**: critical

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 1 (PR #147 - Session log created after completion, not early)

**Category**: Logging

**Source**: PR #147 retrospective analysis (2025-12-20-pr-147-comment-2637248710-failure.md)

## Template Format

```markdown
# Session Log: [Date] - [Purpose]

## Protocol Compliance

### Phase 1: Serena Initialization
- [x] mcp__serena__activate_project
- [x] mcp__serena__initial_instructions

### Phase 2: Context Retrieval
- [x] Read .agents/HANDOFF.md
- [x] Read [relevant context files]

### Phase 3: Session Log Creation
- [x] Created this file

### Phase 8: Artifact Updates
- [ ] Updated tasks.md with current status
- [ ] Updated HANDOFF.md with session summary

## Work Completed

[Track progress here]
```

## Verification

Session log created within first 5 tool calls:

```bash
# After Phase 2
ls -lt .agents/sessions/*.json | head -1
# Should show today's date and session number
```

## Related Skills

- Skill-Init-001: Serena initialization (blocking gate)
- Skill-Protocol-004: RFC 2119 MUST requirements with verification evidence
- Skill-PR-Comment-002: Session-specific work tracking
