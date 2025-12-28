# PRD: Fix Acknowledged vs Resolved Gap in PR Maintenance Workflow

## Introduction

The PR maintenance workflow incorrectly equates "acknowledged" (eyes reaction added) with "addressed" (issue fixed and thread resolved). This causes the script to report "no action needed" for PRs with acknowledged but unresolved bot comments.

**Evidence**: PR #365 had 5 bot comments with eyes reactions but all threads remained unresolved. The script output was "rjmurillo-bot is author, no action needed -> maintenance only" despite all 5 threads requiring resolution.

**Root Cause**: The `Get-UnacknowledgedComments` function only checks `reactions.eyes = 0`. Comments with eyes reactions are incorrectly assumed to be fully addressed.

## Goals

1. Detect PRs with acknowledged but unresolved threads so they appear in ActionRequired
2. Prevent false negatives where unresolved threads are missed
3. Maintain backward compatibility with existing acknowledgment workflow
4. Provide clear distinction between "acknowledged" and "resolved" states

## Non-Goals

1. Auto-resolve threads (already handled by separate script)
2. Change eyes reaction semantics (still means "acknowledged for processing")
3. Modify pr-comment-responder workflow (already checks resolution)
4. Change REST API usage for comments (continue using existing endpoint)

## User Stories

### Story 1: Detect Unresolved Threads

**As** rjmurillo-bot
**I need** to detect conversation threads that are unresolved
**So that** I can take action to address them

**INVEST Criteria**:

- **Independent**: Can be implemented without other features
- **Negotiable**: Implementation approach (new function vs extend existing) is flexible
- **Valuable**: Prevents PRs from being incorrectly marked as complete
- **Estimable**: Clear scope with API query and function implementation
- **Small**: Single function addition with tests
- **Testable**: Can verify with mock GraphQL responses

**Acceptance Criteria**:

1. Function `Get-UnresolvedReviewThreads` returns all threads where `isResolved = false`
2. Function uses GraphQL API (not REST) to access thread resolution status
3. Function returns empty array when all threads are resolved
4. Function handles GraphQL API failure gracefully (logs warning, returns empty array)
5. Function accepts Owner, Repo, and PRNumber parameters

### Story 2: Distinguish Acknowledged from Resolved

**As** a PR maintainer
**I need** the workflow to distinguish between "acknowledged" and "resolved"
**So that** no bot feedback goes unaddressed

**INVEST Criteria**:

- **Independent**: Builds on Story 1 but does not depend on other features
- **Negotiable**: Can use function composition or single monolithic function
- **Valuable**: Fixes the core gap where acknowledged comments are assumed resolved
- **Estimable**: Clear input (comments + threads) and output (unaddressed comments)
- **Small**: Single function with boolean logic
- **Testable**: Can verify with test fixtures covering all combinations

**Acceptance Criteria**:

1. Function `Get-UnaddressedComments` returns comments where `reactions.eyes = 0` OR `isResolved = false`
2. Comment is NOT returned if `reactions.eyes > 0` AND `isResolved = true`
3. Comment IS returned if `reactions.eyes = 0` (regardless of isResolved)
4. Comment IS returned if `isResolved = false` (regardless of reactions.eyes)
5. Function reuses existing `Get-PRComments` and new `Get-UnresolvedReviewThreads`

### Story 3: Update PR Classification Logic

**As** the Invoke-PRMaintenance script
**I need** to check both acknowledgment AND thread resolution
**So that** PRs are correctly classified as needing action or not

**INVEST Criteria**:

- **Independent**: Uses functions from Story 1 and 2, no external dependencies
- **Negotiable**: Can integrate at different points in the decision flow
- **Valuable**: Directly fixes the bug where PR #365 was incorrectly classified
- **Estimable**: Single line change in existing code path
- **Small**: Minimal code change (function call substitution)
- **Testable**: Can verify with integration test using real PR #365 data

**Acceptance Criteria**:

1. Line ~1401 in `Invoke-PRMaintenance.ps1` calls `Get-UnaddressedComments` instead of `Get-UnacknowledgedComments`
2. Variable name changes from `$unacked` to `$unaddressed` for clarity
3. PRs with acknowledged but unresolved comments appear in ActionRequired
4. PRs with all threads resolved do not appear in ActionRequired
5. Existing behavior for unacknowledged comments is preserved

## Functional Requirements

### FR1: GraphQL Thread Resolution Query

The system must query GitHub GraphQL API to retrieve thread resolution status.

**API Endpoint**: `POST /graphql`

**Query Structure**:

```graphql
query {
    repository(owner: "$Owner", name: "$Repo") {
        pullRequest(number: $PR) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes { databaseId }
                    }
                }
            }
        }
    }
}
```

**Output**: Array of thread objects with `id`, `isResolved`, and first comment `databaseId`

### FR2: Unresolved Thread Detection Function

Function signature:

```powershell
function Get-UnresolvedReviewThreads {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PR
    )
    # Returns: Array of thread objects where isResolved = false
}
```

**Behavior**:

- Query GraphQL API for all review threads
- Filter to threads where `isResolved = false`
- Return empty array if no unresolved threads
- Return empty array on API failure (log warning)
- Follow Skill-PowerShell-002: Always return array type, never $null

### FR3: Unaddressed Comment Detection Function

Function signature:

```powershell
function Get-UnaddressedComments {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [array]$Comments = $null
    )
    # Returns: Array of comments that are either unacknowledged OR unresolved
}
```

**Logic**:

1. Fetch comments via `Get-PRComments` if not provided
2. Query unresolved threads via `Get-UnresolvedReviewThreads`
3. Extract comment IDs from unresolved threads
4. Filter comments where: `user.type = 'Bot' AND (reactions.eyes = 0 OR id in unresolvedCommentIds)`
5. Return filtered array (empty if none match)

### FR4: Integration Point Update

**Location**: `scripts/Invoke-PRMaintenance.ps1`, line ~1401

**Change**:

```powershell
# BEFORE
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unacked.Count -gt 0

# AFTER
$unaddressed = Get-UnaddressedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unaddressed.Count -gt 0
```

**Impact**: PRs with `reactions.eyes > 0` but `isResolved = false` will now be detected as needing action.

## Design Considerations

### Option A: Extend Existing Function (Rejected)

Add `-IncludeUnresolved` switch to `Get-UnacknowledgedComments`.

**Pros**: Minimal code changes
**Cons**: Function name is misleading, mixes two responsibilities

### Option B: New Function (Selected)

Create separate `Get-UnaddressedComments` function.

**Pros**:

- Clear semantic meaning
- Single responsibility per function
- Backward compatibility preserved
- Easier to test in isolation

**Cons**: Slightly more code

**Decision**: Use Option B for clarity and maintainability.

### Semantic Model

```text
Comment Lifecycle:

[NEW] -> [ACKNOWLEDGED] -> [REPLIED] -> [RESOLVED]

State Checks:
  NEW:          reactions.eyes = 0, isResolved = false
  ACKNOWLEDGED: reactions.eyes > 0, isResolved = false
  REPLIED:      reactions.eyes > 0, isResolved = false, has reply
  RESOLVED:     reactions.eyes > 0, isResolved = true

Get-UnacknowledgedComments: Detects [NEW] only
Get-UnaddressedComments:    Detects [NEW], [ACKNOWLEDGED], [REPLIED]
```

## Technical Considerations

### API Rate Limits

GraphQL queries count against `graphql` resource limit (5000/hour).

**Mitigation**:

- Script already checks rate limits before execution
- Add `graphql` to `Test-RateLimitSafe` resource checks (threshold: 100)
- Query once per PR (not per comment)

### Error Handling

GraphQL API may fail due to:

1. Rate limit exceeded
2. Network issues
3. Invalid query syntax
4. Repository not found

**Handling Strategy**:

- Log warning on GraphQL failure
- Return empty array (fail-safe: assume no unresolved threads)
- Script continues processing remaining PRs

### Performance Impact

**Current**: 1 REST API call per PR (comments)
**After**: 1 REST + 1 GraphQL call per PR

**Estimated Impact**: +50ms per PR (GraphQL query latency)
**Total for 20 PRs**: +1 second

This is acceptable given the 45-minute timeout and typical run time of <60s.

## Success Metrics

### Functional Validation

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| 1 | PR #365 appears in ActionRequired | Run script against live repo, check output |
| 2 | Reason is UNRESOLVED_THREADS or similar | Inspect ActionRequired entry |
| 3 | All 5 comments flagged | `Get-UnaddressedComments` returns count = 5 |
| 4 | Resolved threads not flagged | Mock PR with all `isResolved = true`, count = 0 |
| 5 | Unacknowledged comments still detected | Mock PR with `reactions.eyes = 0`, count > 0 |

### Test Coverage

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| All resolved | eyes=1, isResolved=true | Count = 0 |
| Acknowledged but unresolved | eyes=1, isResolved=false | Count > 0 |
| Unacknowledged | eyes=0, isResolved=false | Count > 0 |
| Mixed state | Some acked+resolved, some unresolved | Count = unresolved only |
| GraphQL API failure | API returns error | Count = unacked only (fallback) |

### Acceptance Gates

Script output must include:

```text
PRs Requiring Action:

| PR | Author | Category | Action |
|----|--------|----------|--------|
| #365 | rjmurillo-bot | agent-controlled | /pr-review via pr-comment-responder |
```

Reason field must indicate unresolved threads (not just unacknowledged).

## Dependencies and Risks

### Dependencies

| Dependency | Type | Risk Level | Mitigation |
|------------|------|------------|------------|
| GitHub GraphQL API | External | Low | Graceful fallback on failure |
| `Get-PRComments` function | Internal | None | Existing, tested function |
| PowerShell 7.0+ | Runtime | None | Already required by script |
| GitHub CLI (gh) | Tool | Low | Already required and tested |

### Risks

**Risk 1: GraphQL Schema Changes**

**Probability**: Low
**Impact**: High (function breaks)
**Mitigation**: Use stable fields (`isResolved` is core feature), add schema version check

**Risk 2: Performance Degradation**

**Probability**: Low
**Impact**: Medium (slower runs)
**Mitigation**: Query threads once per PR, cache results if needed

**Risk 3: False Positives**

**Probability**: Low
**Impact**: Medium (unnecessary /pr-review invocations)
**Mitigation**: Comprehensive test coverage, dry-run validation before merge

**Risk 4: Breaking Existing Workflow**

**Probability**: Low
**Impact**: High (script stops working)
**Mitigation**: Preserve `Get-UnacknowledgedComments` unchanged, add new function separately

## Implementation Plan

### Phase 1: Add Functions

1. Add `Get-UnresolvedReviewThreads` to `scripts/Invoke-PRMaintenance.ps1`
2. Add `Get-UnaddressedComments` to `scripts/Invoke-PRMaintenance.ps1`
3. Add unit tests for both functions

**Acceptance**: Tests pass for all scenarios in Success Metrics table

### Phase 2: Integrate

1. Update line ~1401 to call `Get-UnaddressedComments`
2. Update ActionRequired reason to distinguish UNRESOLVED_THREADS from UNACKNOWLEDGED
3. Add integration test using PR #365 data

**Acceptance**: PR #365 scenario correctly classified as ActionRequired

### Phase 3: Document

1. Update `.agents/architecture/bot-author-feedback-protocol.md` glossary
2. Add "Acknowledged vs Resolved" section to protocol
3. Update function docstrings with lifecycle model

**Acceptance**: Documentation clearly explains state transitions

## Open Questions

1. Should GraphQL failure trigger script exit or continue with fallback behavior?
   - **Recommendation**: Continue with fallback (unacked-only check) to avoid workflow disruption

2. Should ActionRequired distinguish between UNACKNOWLEDGED vs UNRESOLVED_THREADS reasons?
   - **Recommendation**: Yes, use separate reasons for better diagnostics

3. Should we add GraphQL queries to existing `Test-RateLimitSafe` check?
   - **Recommendation**: Yes, add `graphql` resource with threshold of 100

4. Should we cache GraphQL results if multiple PRs are processed?
   - **Recommendation**: No, queries are per-PR and runtime impact is minimal

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `scripts/Invoke-PRMaintenance.ps1` | ADD | `Get-UnresolvedReviewThreads` function (after line ~500) |
| `scripts/Invoke-PRMaintenance.ps1` | ADD | `Get-UnaddressedComments` function (after `Get-UnresolvedReviewThreads`) |
| `scripts/Invoke-PRMaintenance.ps1` | MODIFY | Line ~1401: Replace `Get-UnacknowledgedComments` with `Get-UnaddressedComments` |
| `scripts/Invoke-PRMaintenance.ps1` | MODIFY | Line ~207: Add `graphql` to `Test-RateLimitSafe` resource list |
| `scripts/tests/Invoke-PRMaintenance.Tests.ps1` | ADD | Test suite for `Get-UnresolvedReviewThreads` |
| `scripts/tests/Invoke-PRMaintenance.Tests.ps1` | ADD | Test suite for `Get-UnaddressedComments` |
| `.agents/architecture/bot-author-feedback-protocol.md` | MODIFY | Glossary: Add "Acknowledged vs Resolved" entry |

## Assumptions

1. GitHub GraphQL API `isResolved` field is reliable and up-to-date
2. Thread resolution is binary (true/false), no intermediate states
3. All bot comments are part of review threads (not standalone issue comments)
4. First comment in thread chain is sufficient to identify thread origin
5. GraphQL query returning empty array on error is acceptable fallback

## Related Context

- **Tracking Issue**: #402 (PR maintenance visibility gap)
- **Example PR**: #365 (5 acknowledged but unresolved threads)
- **Protocol Document**: `.agents/architecture/bot-author-feedback-protocol.md`
- **Existing Tool**: `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1` (demonstrates GraphQL pattern)
- **Gap Analysis**: `.agents/qa/PR-402/2025-12-26-gap-diagnostics-02.md` (Five Whys root cause)

## Appendix: Test Fixtures

### Fixture 1: PR #365 Equivalent

```json
{
  "comments": [
    {"id": 1, "user": {"type": "Bot"}, "reactions": {"eyes": 1}},
    {"id": 2, "user": {"type": "Bot"}, "reactions": {"eyes": 1}},
    {"id": 3, "user": {"type": "Bot"}, "reactions": {"eyes": 1}},
    {"id": 4, "user": {"type": "Bot"}, "reactions": {"eyes": 1}},
    {"id": 5, "user": {"type": "Bot"}, "reactions": {"eyes": 1}}
  ],
  "threads": [
    {"id": "T1", "isResolved": false, "comments": [{"databaseId": 1}]},
    {"id": "T2", "isResolved": false, "comments": [{"databaseId": 2}]},
    {"id": "T3", "isResolved": false, "comments": [{"databaseId": 3}]},
    {"id": "T4", "isResolved": false, "comments": [{"databaseId": 4}]},
    {"id": "T5", "isResolved": false, "comments": [{"databaseId": 5}]}
  ]
}
```

**Expected**: `Get-UnaddressedComments` returns count = 5

### Fixture 2: Fully Resolved PR

```json
{
  "comments": [
    {"id": 1, "user": {"type": "Bot"}, "reactions": {"eyes": 1}},
    {"id": 2, "user": {"type": "Bot"}, "reactions": {"eyes": 1}}
  ],
  "threads": [
    {"id": "T1", "isResolved": true, "comments": [{"databaseId": 1}]},
    {"id": "T2", "isResolved": true, "comments": [{"databaseId": 2}]}
  ]
}
```

**Expected**: `Get-UnaddressedComments` returns count = 0

### Fixture 3: Mixed State

```json
{
  "comments": [
    {"id": 1, "user": {"type": "Bot"}, "reactions": {"eyes": 0}},
    {"id": 2, "user": {"type": "Bot"}, "reactions": {"eyes": 1}},
    {"id": 3, "user": {"type": "Bot"}, "reactions": {"eyes": 1}}
  ],
  "threads": [
    {"id": "T1", "isResolved": false, "comments": [{"databaseId": 1}]},
    {"id": "T2", "isResolved": false, "comments": [{"databaseId": 2}]},
    {"id": "T3", "isResolved": true, "comments": [{"databaseId": 3}]}
  ]
}
```

**Expected**: `Get-UnaddressedComments` returns count = 2 (IDs 1 and 2)
