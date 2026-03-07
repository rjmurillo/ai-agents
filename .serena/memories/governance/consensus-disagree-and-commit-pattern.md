# DISAGREE AND COMMIT Consensus Pattern

## Pattern

Create follow-up issue for dissenting concerns to achieve consensus without blocking the primary decision, enabling progress with documented dissent.

## Problem

Multi-agent debates can deadlock when one agent raises a valid concern that doesn't invalidate the primary solution but prevents unanimous consensus. Forcing consensus suppresses valuable perspectives. Blocking on dissent prevents progress.

## Solution

**When agent raises valid concern during debate**:

1. **Acknowledge the concern**: "This is a valid hypothesis worth investigating"
2. **Assess criticality**: Does it block the primary decision?
   - **Blocking**: Concern must be resolved now (e.g., security vulnerability)
   - **Non-blocking**: Concern is important but doesn't invalidate primary solution
3. **If non-blocking**: Create follow-up issue for investigation
4. **Document dissent**: Agent votes "DISAGREE AND COMMIT"
5. **Proceed with consensus**: Primary decision approved, dissent recorded

## Evidence

**Session 826** (2026-01-13): ADR-040 amendment debate (6 agents):

- **Primary decision**: Standardize on block-style YAML arrays
- **Dissenting concern**: Independent-thinker hypothesized CRLF line endings might be root cause, not inline arrays
- **Resolution**:
  - Created Issue #896 to investigate CRLF line endings
  - Independent-thinker voted "DISAGREE AND COMMIT"
  - Consensus achieved: 5 ACCEPT, 1 DISAGREE AND COMMIT
  - Primary decision proceeded

**Outcome**: Both concerns addressed (block-style standardization AND CRLF investigation), no deadlock.

## Benefits

| Approach | Pros | Cons |
|----------|------|------|
| **Force unanimous consent** | Clean consensus | Suppresses dissent, groupthink risk |
| **Block on any dissent** | Thorough vetting | Deadlock risk, slow progress |
| **DISAGREE AND COMMIT** | Progress + dissent preserved | Requires trust, follow-up discipline |

## Voting Outcomes

| Vote | Meaning | Action |
|------|---------|--------|
| ACCEPT | Full agreement | Proceed |
| ACCEPT WITH CONCERNS | Conditional agreement | Document concerns, proceed |
| DISAGREE AND COMMIT | Dissent recorded, commit to decision | Create follow-up issue, proceed |
| REJECT | Blocking concern | Resolve before proceeding |

## Implementation Requirements

1. **Follow-up issue MUST be created** (not optional)
2. **Dissent MUST be documented** in debate log
3. **Follow-up issue MUST reference** original decision
4. **Dissenting agent should be assigned** to follow-up issue

## Impact

- **Atomicity**: 88%
- **Domain**: multi-agent-coordination
- **Deadlock Prevention**: Enables progress without suppressing dissent
- **Trust Requirement**: HIGH (agents must trust follow-up will happen)

## Anti-Patterns

❌ **False consensus**: Ignoring dissent without follow-up
❌ **Scope creep**: Expanding primary decision to address dissent
❌ **Suppression**: Voting "ACCEPT" when you actually disagree
❌ **Abandonment**: Creating follow-up issue but never addressing it

## Related

- [[debate-002-everything-deterministic-evaluation]] - Debate framework
- [[orchestration-003-orchestrator-first-routing]] - Multi-agent coordination
- [[quality-critique-escalation]] - Escalation patterns

## Source

- Session: 826 (2026-01-13)
- Retrospective: `.agents/retrospective/2026-01-13-fix-tools-frontmatter-retrospective.md`
- Learning: L4 (Phase 4, Lines 548-557)
- Debate log: `.agents/critique/ADR-040-amendment-2026-01-13-debate-log.md`
- Follow-up: Issue #896 (CRLF investigation)
