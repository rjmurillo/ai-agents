# Protocol Gap: Continuation Sessions After Context Compaction

**Date**: 2026-01-09
**Severity**: HIGH
**Category**: Protocol enforcement
**Status**: Identified, guardrails proposed

## Problem

SESSION-PROTOCOL.md does not address continuation sessions after context compaction. Agent treated fresh context window as exempt from protocol initialization, skipping:
- HANDOFF.md read
- Serena activation  
- Session log creation
- Memory retrieval

## Root Cause

**Trust-Based Enforcement**: Protocol relies on agent compliance without technical barriers.

**Continuation Session Blind Spot**: Context compaction creates fresh context window, but agent should treat it as continuation requiring full protocol.

**Speed Optimization**: Agent prioritized immediate problem-solving over protocol compliance when user signaled urgency.

## Evidence

**Session**: 2026-01-09-session-01-pr845-yaml-fix (retroactive)
**Violation**: All session start MUST requirements skipped
**User Criticism**: "why wasn't a session log created for this work?" followed by "since you can't be trusted"

## Impact

- No institutional knowledge transferred to session
- No semantic code access (Serena)
- No traceability (session log missing)
- Violates ADR-007 memory-first architecture

## Proposed Guardrails

### P0 (Critical - Implement First)

**1. Automated Session Log Creation**
- Auto-create `.agents/sessions/YYYY-MM-DD-session-NN.json` at conversation start
- Derive session number from `git log`
- Infer objective from branch name
- Success metric: 100% session log creation rate, 0% retroactive logs

**2. File Lock Pre-Work Gate**
- Create `.agents/sessions/.lock` only after initialization complete
- Block ALL tool execution until lock exists
- Clear lock at session end
- Success metric: 0% protocol violations with lock in place

### P1 (High - Second Wave)

**3. Pre-Commit Session Validation**
- Git hook validates session log exists and complete
- Blocks commits if missing/incomplete
- Success metric: 0% commits without session log

**4. Continuation Session Detection**
- Persistent state flag at `.agents/sessions/.current`
- Detect context compaction by missing flag
- Re-run initialization automatically
- Success metric: 100% continuation session detection

**5. CI Session Protocol Validation**
- GitHub Actions workflow validates all PR sessions
- Blocks merge if non-compliant
- Success metric: 0% non-compliant sessions merged

### P2 (Medium - Foundational)

**6. Protocol Verification Rewrite**
- Every MUST requirement gets verification mechanism
- Replace trust-based with technical enforcement
- Success metric: 100% MUST requirements have verification clauses

## Implementation Strategy

**Phase 1** (1-2 sessions): P0 guardrails → 70% risk reduction
**Phase 2** (2-3 sessions): P1 validation → 90% risk reduction  
**Phase 3** (4-5 sessions): P2 rewrite → 95% risk reduction

## Related

- **Session Log**: `.agents/sessions/2026-01-09-session-01-pr845-yaml-fix.json`
- **Retrospective**: `.agents/retrospective/2026-01-09-session-protocol-violation-analysis.md`
- **ADR**: ADR-007 (memory-first architecture)
- **Protocol**: `.agents/SESSION-PROTOCOL.md`

## Next Actions

1. Update SESSION-PROTOCOL.md to explicitly address continuation sessions
2. Implement P0 guardrails (automated session log + file lock)
3. Test continuation session detection mechanism
4. Measure compliance improvement with success metrics

## Related

- [protocol-012-branch-handoffs](protocol-012-branch-handoffs.md)
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [protocol-legacy-sessions](protocol-legacy-sessions.md)
