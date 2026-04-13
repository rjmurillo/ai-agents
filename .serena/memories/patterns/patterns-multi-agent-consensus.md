# Multi-Agent Consensus Patterns

## DISAGREE AND COMMIT

A consensus mechanism where agents can express disagreement while still committing to the group decision.

### When to Use

- One agent raises valid concern that does not invalidate primary solution
- Concern requires separate investigation
- Blocking on concern would delay urgent fix

### Protocol

1. Agent votes DISAGREE AND COMMIT (not BLOCK)
2. Dissenting rationale documented in debate log
3. Follow-up issue created for deferred investigation
4. Consensus achieved: primary decision proceeds

### Example (Session 826)

**Scenario**: ADR-040 YAML array format amendment

**Vote Results**:

- Architect: ACCEPT
- Critic: ACCEPT
- Security: ACCEPT
- Analyst: ACCEPT
- High-level-advisor: ACCEPT
- Independent-thinker: DISAGREE AND COMMIT

**Dissent**: "CRLF line endings may be actual root cause, not array format"

**Resolution**: Issue #896 created for CRLF investigation. Amendment proceeded.

### Benefits

- Progress not blocked by minority dissent
- Dissenting views documented and tracked
- Follow-up work captured in issues
- Consensus achieved without suppressing disagreement

### Contrast with BLOCK

| DISAGREE AND COMMIT | BLOCK |
|---------------------|-------|
| Concern is P1/P2 | Concern is P0 |
| Deferred investigation acceptable | Immediate resolution required |
| Primary solution valid | Primary solution flawed |
| Creates follow-up issue | Requires re-work |

## Evidence

- Session 826: 5 ACCEPT, 1 DISAGREE AND COMMIT achieved consensus
- Issue #896 tracks deferred CRLF investigation
- ADR-040 amendment completed successfully

## Related

- [[learnings-2026-01]] - Learning L4: DISAGREE AND COMMIT Consensus
- `.agents/critique/ADR-040-amendment-2026-01-13-debate-log.md`
