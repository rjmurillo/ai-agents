# Skill-Protocol-004: RFC 2119 MUST Requirements Evidence

**Statement**: Implement RFC 2119 MUST requirements with verification evidence

**Context**: Any phase transition in protocol

**Trigger**: When protocol document uses RFC 2119 keywords (MUST, SHOULD, MAY)

**Action**: Log verification evidence before proceeding (tool output, file content)

**Evidence**: Transcript shows verification tool call and confirmation

**Anti-pattern**: Proceeding based on memory of prior action without verification

**Atomicity**: 96%

**Tag**: critical

**Impact**: 10/10

**Created**: 2025-12-20

**Validated**: 1 (PR #147 - Agent claimed compliance without verification evidence)

**Category**: Protocol

**Source**: PR #147 retrospective analysis (2025-12-20-pr-147-comment-2637248710-failure.md)

## RFC 2119 Compliance Pattern

When protocol states "Agent MUST [action]":

1. **Execute**: Perform the action via tool call
2. **Verify**: Read output/artifact to confirm success
3. **Log**: Record evidence in session log
4. **Gate**: Do not proceed without all three

## Evidence Examples

### MUST Create Session Log

```markdown
## Phase 3: Session Log Creation

Evidence:
- Tool: Write(.agents/sessions/2025-12-20-session-01.md)
- Verification: Read(.agents/sessions/2025-12-20-session-01.md) - 45 lines
- Confirmed: File exists with Protocol Compliance section
```

### MUST Update HANDOFF.md

```markdown
## Phase 8: HANDOFF Update

Evidence:
- Tool: Edit(.agents/HANDOFF.md, old="Last Updated: 2025-12-19", new="Last Updated: 2025-12-20")
- Verification: Read(.agents/HANDOFF.md) - shows "Last Updated: 2025-12-20"
- Confirmed: Session summary added at line 594
```

## Verification Script

Before marking phase complete:

```bash
# Check session log has evidence sections
grep -A 3 "Evidence:" .agents/sessions/YYYY-MM-DD-session-NN.md

# Should show:
# - Tool: [tool call]
# - Verification: [verification call]
# - Confirmed: [success message]
```

## Related Skills

- Skill-Init-002: Comprehensive Protocol Verification (retrospective-2025-12-17-protocol-compliance)
- Skill-Verification-003: Verify artifact state matches API state using diff
- Skill-Logging-002: Create session log with checklist template
