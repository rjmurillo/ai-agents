# PR #402 Retrospective: Acknowledged vs Resolved

**Date**: 2025-12-26
**Issue**: #402 (PR maintenance visibility gap)
**Example PR**: #365 (5 acknowledged but unresolved threads)
**Outcome**: Success - bug fixed, protocol documented, live validation confirmed

## Key Learnings

### Root Cause Discovery

**Problem**: PR #365 had 5 bot comments with eyes reactions (acknowledged) but all review threads remained unresolved. Script reported "no action needed."

**Five Whys Trace**:
1. Why "no action needed"? → Function only checked acknowledgment (eyes reaction)
2. Why only acknowledgment? → Semantic model assumed acknowledged = addressed
3. Why conflated states? → Thread resolution status not checked
4. Why not checked? → REST API doesn't expose `isResolved` field
5. Why not GraphQL? → REST simpler; GraphQL requirement discovered during lifecycle analysis

**Root Cause**: Incomplete semantic model (acknowledged ≠ resolved) + API surface gap (GraphQL required)

### Lifecycle Model

**State Machine**:
```text
NEW (eyes=0, unresolved) 
  → ACKNOWLEDGED (eyes>0, unresolved)
  → REPLIED (eyes>0, unresolved, has reply)
  → RESOLVED (eyes>0, isResolved=true)
```

**Functions**:
- `Get-UnacknowledgedComments`: Detects NEW only
- `Get-UnaddressedComments`: Detects NEW + ACKNOWLEDGED + REPLIED (all unresolved states)

### Technical Solution

**New Functions**:
1. `Get-UnresolvedReviewThreads` (GraphQL query for `isResolved` status)
2. `Get-UnaddressedComments` (checks acknowledgment OR resolution)

**GraphQL Query Pattern**:
```graphql
repository -> pullRequest -> reviewThreads -> isResolved
```

**Integration Point**: Line ~1401 in `Invoke-PRMaintenance.ps1`

### Testing Outcomes

- **Tests Added**: 13 new tests (bot detection) + 6 tests (acknowledgment/resolution)
- **Test Coverage**: 154 tests passing, 1 skipped
- **Test Gap**: `TotalPRs` property + `GITHUB_STEP_SUMMARY` output (entry point code)
- **Risk Mitigation**: Code isolated in entry point, no core logic changes

### Validation Results

- **Live Execution**: All 15 PRs processed correctly
- **PR #365**: All 5 acknowledged-but-unresolved threads correctly detected
- **Fixtures Match**: PRD test fixtures matched real API responses exactly

## Success Factors

1. **Lifecycle State Diagram**: Eliminated semantic confusion (acknowledged ≠ resolved)
2. **GraphQL Discovery**: API requirement identified during design, not late in implementation
3. **Test-Driven PRD**: Fixtures in appendix drove implementation
4. **Existing Patterns**: Reference GraphQL query in `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1`
5. **Critic Gate**: PRD approved on first attempt (no rework)

## Process Improvements

### P0 (Critical)
- **Lifecycle modeling**: Create state diagrams for all multi-state entities
- **GraphQL-first analysis**: Check GraphQL capabilities before assuming REST sufficient
- **Integration tests**: Required for all API-dependent code before merge

### P1 (High)
- **Contract testing**: Validate mock structures match real API schemas
- **Entry point testing**: Integration tests for code blocked by dot-sourcing pattern
- **Test gap documentation**: Explicit risk acceptance in session logs

### P2 (Medium)
- **API response recording**: Capture real responses for test fixtures
- **Semantic model library**: Catalog all state machines
- **Lifecycle DSL**: Formalize state machine definitions

## Extracted Skills

### New Skills (All ≥88% Atomicity)

1. **Skill-Design-008** (95%): Acknowledged (reaction) ≠ Resolved (thread status) requires explicit lifecycle model
2. **Skill-Implementation-006** (92%): Check GraphQL capabilities before assuming REST API sufficient for feature
3. **Skill-Testing-007** (90%): Mock data structures must match real API response schemas including property casing
4. **Skill-Testing-008** (88%): Code in entry points requires integration tests when unit tests blocked by dot-sourcing

### Updated Skills

- **Skill-Planning-004**: Add integration test requirement before merge

### Tagged Helpful

- Skill-Design-007 (lifecycle diagrams)
- Skill-Testing-003 (real API fixtures)
- Skill-Implementation-005 (GraphQL reference)
- Skill-Planning-004 (critic checkpoint)
- Skill-Documentation-001 (documentation-first)

## Anti-Patterns Avoided

- ❌ Scope creep without validation → ✅ Critic gate caught expansion
- ❌ Mock-reality gaps → ✅ Real API fixtures prevented mismatches
- ❌ Semantic confusion → ✅ Lifecycle model provided clarity
- ❌ Late API discovery → ✅ GraphQL requirement identified in design

## Related Context

- **Tracking Issue**: #402
- **Example PR**: #365
- **Protocol**: `.agents/architecture/bot-author-feedback-protocol.md`
- **Implementation**: `scripts/Invoke-PRMaintenance.ps1` (lines 588-753, 1597-1611)
- **Tests**: `scripts/tests/Invoke-PRMaintenance.Tests.ps1`
- **Commits**: 2d3cb20 (implementation), 8744ef4 (docs), c389dca (merge)

## ROTI Assessment

**Score**: 4 (Exceptional)

**Benefits**:
- 4 atomic skills extracted
- Root cause pattern documented
- Testing gaps identified
- Lifecycle modeling validated
- GraphQL integration pattern established

**Time**: ~4 hours

**Verdict**: Continue - high-value learnings, reusable patterns
