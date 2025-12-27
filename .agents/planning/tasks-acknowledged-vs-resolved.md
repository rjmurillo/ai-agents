# Task Breakdown: Fix Acknowledged vs Resolved Gap

## Source

- PRD: `.agents/planning/PRD-acknowledged-vs-resolved.md`
- Tracking Issue: #402
- Example PR: #365

## Summary

| Complexity | Count |
|------------|-------|
| S | 7 |
| M | 5 |
| L | 1 |
| **Total** | **13** |

## Tasks

### Milestone 1: Add Core Functions

**Goal**: Implement GraphQL query and detection functions with comprehensive test coverage

---

#### Task: Implement GraphQL thread resolution query

**ID**: TASK-001
**Type**: Feature
**Complexity**: M

**Description**
Add GraphQL query to retrieve review thread resolution status for a pull request.

**Acceptance Criteria**
- [ ] Query uses GraphQL API endpoint POST /graphql
- [ ] Query structure matches FR1 specification (repository -> pullRequest -> reviewThreads)
- [ ] Query retrieves first 100 threads with id, isResolved, and first comment databaseId
- [ ] Query accepts Owner, Repo, and PR number as parameters
- [ ] Query handles API failure gracefully (returns error info)

**Dependencies**
- None

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Add GraphQL query construction

---

#### Task: Implement Get-UnresolvedReviewThreads function

**ID**: TASK-002
**Type**: Feature
**Complexity**: M

**Description**
Create function to detect review threads that remain unresolved using GraphQL API.

**Acceptance Criteria**
- [ ] Function signature matches FR2 specification (Owner, Repo, PR parameters)
- [ ] Function returns array of thread objects where isResolved = false
- [ ] Function returns empty array when all threads are resolved
- [ ] Function returns empty array on API failure with logged warning
- [ ] Function follows Skill-PowerShell-002 (always returns array, never $null)
- [ ] Function includes CmdletBinding and proper parameter attributes

**Dependencies**
- TASK-001: GraphQL query implementation

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Add function after line ~500

---

#### Task: Write unit tests for Get-UnresolvedReviewThreads

**ID**: TASK-003
**Type**: Chore
**Complexity**: S

**Description**
Create Pester tests for Get-UnresolvedReviewThreads covering all scenarios in Success Metrics table.

**Acceptance Criteria**
- [ ] Test case: All threads resolved returns empty array
- [ ] Test case: Some threads unresolved returns correct count
- [ ] Test case: No threads exist returns empty array
- [ ] Test case: GraphQL API failure returns empty array with warning
- [ ] Test case: Parameters are validated correctly
- [ ] All tests pass with green status

**Dependencies**
- TASK-002: Get-UnresolvedReviewThreads implementation

**Files Affected**
- `scripts/tests/Invoke-PRMaintenance.Tests.ps1`: Add test suite

---

#### Task: Implement Get-UnaddressedComments function

**ID**: TASK-004
**Type**: Feature
**Complexity**: M

**Description**
Create function to detect comments that are either unacknowledged OR unresolved.

**Acceptance Criteria**
- [ ] Function signature matches FR3 specification
- [ ] Function accepts optional Comments array parameter
- [ ] Function calls Get-PRComments if Comments not provided
- [ ] Function calls Get-UnresolvedReviewThreads to get unresolved thread IDs
- [ ] Function filters comments where user.type = 'Bot' AND (reactions.eyes = 0 OR id in unresolvedCommentIds)
- [ ] Function returns empty array when all comments are addressed
- [ ] Comment with eyes > 0 AND isResolved = true is NOT returned
- [ ] Comment with eyes = 0 OR isResolved = false IS returned

**Dependencies**
- TASK-002: Get-UnresolvedReviewThreads implementation

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Add function after Get-UnresolvedReviewThreads

---

#### Task: Write unit tests for Get-UnaddressedComments

**ID**: TASK-005
**Type**: Chore
**Complexity**: M

**Description**
Create comprehensive Pester tests for Get-UnaddressedComments covering all state combinations.

**Acceptance Criteria**
- [ ] Test case: All resolved (eyes=1, isResolved=true) returns count = 0 (Fixture 2)
- [ ] Test case: Acknowledged but unresolved (eyes=1, isResolved=false) returns count > 0 (Fixture 1)
- [ ] Test case: Unacknowledged (eyes=0, isResolved=false) returns count > 0
- [ ] Test case: Mixed state returns only unaddressed comments (Fixture 3)
- [ ] Test case: GraphQL API failure falls back to unacknowledged-only check
- [ ] Test case: Non-bot comments are excluded
- [ ] All test fixtures from PRD Appendix are covered
- [ ] All tests pass with green status

**Dependencies**
- TASK-004: Get-UnaddressedComments implementation

**Files Affected**
- `scripts/tests/Invoke-PRMaintenance.Tests.ps1`: Add test suite

---

### Milestone 2: Integration and Validation

**Goal**: Integrate new functions into PR classification logic and validate with PR #365 data

---

#### Task: Update PR classification logic to use Get-UnaddressedComments

**ID**: TASK-006
**Type**: Feature
**Complexity**: S

**Description**
Replace Get-UnacknowledgedComments call with Get-UnaddressedComments at integration point.

**Acceptance Criteria**
- [ ] Line ~1401 in Invoke-PRMaintenance.ps1 calls Get-UnaddressedComments
- [ ] Variable name changed from $unacked to $unaddressed
- [ ] No other logic changes in surrounding code
- [ ] Code compiles without syntax errors
- [ ] Existing Get-UnacknowledgedComments function remains unchanged (backward compatibility)

**Dependencies**
- TASK-004: Get-UnaddressedComments implementation

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Modify line ~1401

---

#### Task: Update ActionRequired reason to distinguish unresolved threads

**ID**: TASK-007
**Type**: Feature
**Complexity**: S

**Description**
Add logic to set ActionRequired reason field to distinguish UNRESOLVED_THREADS from UNACKNOWLEDGED.

**Acceptance Criteria**
- [ ] Reason is UNRESOLVED_THREADS when threads are unresolved
- [ ] Reason is UNACKNOWLEDGED when comments lack eyes reaction
- [ ] Reason is combined when both conditions exist
- [ ] Reason field appears in ActionRequired output table
- [ ] Reason provides sufficient diagnostic info for maintainers

**Dependencies**
- TASK-006: Integration point update

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Update reason logic near line ~1401

---

#### Task: Add graphql resource to rate limit check

**ID**: TASK-008
**Type**: Feature
**Complexity**: S

**Description**
Update Test-RateLimitSafe to check graphql resource with threshold of 100.

**Acceptance Criteria**
- [ ] graphql added to resource list at line ~207
- [ ] Threshold set to 100 remaining calls
- [ ] Script exits early if graphql limit too low
- [ ] Warning message mentions graphql resource specifically
- [ ] Existing core/search resource checks remain unchanged

**Dependencies**
- None

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Modify line ~207

---

#### Task: Create integration test for PR #365 scenario

**ID**: TASK-009
**Type**: Chore
**Complexity**: M

**Description**
Add integration test using PR #365 data to verify correct classification.

**Acceptance Criteria**
- [ ] Test uses Fixture 1 from PRD (5 comments with eyes=1, all threads unresolved)
- [ ] Test mocks Get-PRComments to return 5 bot comments
- [ ] Test mocks Get-UnresolvedReviewThreads to return 5 unresolved threads
- [ ] Test verifies Get-UnaddressedComments returns count = 5
- [ ] Test verifies PR is classified as ActionRequired
- [ ] Test verifies reason indicates UNRESOLVED_THREADS
- [ ] Test passes with green status

**Dependencies**
- TASK-006: Integration point update
- TASK-007: Reason field update

**Files Affected**
- `scripts/tests/Invoke-PRMaintenance.Tests.ps1`: Add integration test suite

---

#### Task: Run script against live repo to validate PR #365 detection

**ID**: TASK-010
**Type**: Chore
**Complexity**: L

**Description**
Execute script against live GitHub repo to verify PR #365 appears in ActionRequired output.

**Acceptance Criteria**
- [ ] Script runs without errors
- [ ] PR #365 appears in ActionRequired section
- [ ] All 5 comments are flagged as unaddressed
- [ ] Reason field indicates unresolved threads
- [ ] No false positives (resolved PRs not flagged)
- [ ] Script runtime increase is < 2 seconds compared to baseline
- [ ] Output format matches Success Metrics acceptance gate

**Dependencies**
- TASK-006: Integration point update
- TASK-007: Reason field update
- TASK-008: Rate limit check update

**Files Affected**
- None (validation only)

---

### Milestone 3: Documentation

**Goal**: Document state transitions and update protocol glossary

---

#### Task: Update bot-author-feedback-protocol.md glossary

**ID**: TASK-011
**Type**: Chore
**Complexity**: S

**Description**
Add "Acknowledged vs Resolved" entry to protocol document glossary.

**Acceptance Criteria**
- [ ] Glossary entry defines "Acknowledged" state (eyes reaction added)
- [ ] Glossary entry defines "Resolved" state (thread marked resolved)
- [ ] Glossary entry clarifies distinction between states
- [ ] Entry references Get-UnaddressedComments function
- [ ] Entry includes example scenarios (e.g., PR #365)

**Dependencies**
- TASK-006: Integration point update

**Files Affected**
- `.agents/architecture/bot-author-feedback-protocol.md`: Add glossary entry

---

#### Task: Add "Acknowledged vs Resolved" section to protocol

**ID**: TASK-012
**Type**: Chore
**Complexity**: S

**Description**
Create new protocol section explaining state lifecycle model from PRD.

**Acceptance Criteria**
- [ ] Section includes state transition diagram from PRD (NEW -> ACKNOWLEDGED -> REPLIED -> RESOLVED)
- [ ] Section defines state checks for each lifecycle stage
- [ ] Section explains how Get-UnacknowledgedComments vs Get-UnaddressedComments differ
- [ ] Section references PR #365 as motivating example
- [ ] Section follows protocol document structure and formatting

**Dependencies**
- TASK-011: Glossary update

**Files Affected**
- `.agents/architecture/bot-author-feedback-protocol.md`: Add new section

---

#### Task: Update function docstrings with lifecycle model

**ID**: TASK-013
**Type**: Chore
**Complexity**: S

**Description**
Add comprehensive docstrings to Get-UnresolvedReviewThreads and Get-UnaddressedComments.

**Acceptance Criteria**
- [ ] Docstring includes .SYNOPSIS describing function purpose
- [ ] Docstring includes .DESCRIPTION with lifecycle model reference
- [ ] Docstring includes .PARAMETER for each parameter
- [ ] Docstring includes .EXAMPLE showing typical usage
- [ ] Docstring includes .OUTPUTS describing return type
- [ ] Docstring follows PowerShell comment-based help standards

**Dependencies**
- TASK-012: Protocol section update

**Files Affected**
- `scripts/Invoke-PRMaintenance.ps1`: Update function docstrings

---

## Dependency Graph

```text
TASK-001 → TASK-002 → TASK-003
                    ↘
TASK-001 → TASK-002 → TASK-004 → TASK-005
                                ↘
                                 TASK-006 → TASK-007 → TASK-009
                                         ↘           ↘
                                          TASK-011 → TASK-012 → TASK-013
                                         ↗
TASK-008 ────────────────────────────────┘
                                         ↘
                                          TASK-010

Critical Path: TASK-001 → TASK-002 → TASK-004 → TASK-006 → TASK-007 → TASK-010
```

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| GraphQL schema change breaks query | High | Use stable fields (isResolved is core feature), add version check |
| Performance degradation from extra API call | Medium | Query once per PR, measure runtime impact, add caching if needed |
| False positives trigger unnecessary pr-review invocations | Medium | Comprehensive test coverage with all 3 fixtures, dry-run validation |
| Breaking Get-UnacknowledgedComments disrupts existing workflow | High | Leave existing function unchanged, add new function separately |
| GraphQL rate limit exhaustion | Medium | Add graphql to Test-RateLimitSafe (TASK-008), threshold 100 |
| Test fixtures don't match real PR #365 data | Medium | Validate with live repo execution (TASK-010) before merge |

## Estimate Reconciliation

**Source Document**: PRD-acknowledged-vs-resolved.md
**Source Estimate**: Not provided (PRD focused on scope, not effort)
**Derived Estimate**: 13 tasks (7S + 5M + 1L)
**Difference**: N/A (no source estimate to compare)
**Status**: Not applicable
**Rationale**: PRD provided functional requirements and implementation phases but did not include effort estimates. Task breakdown is based on atomic units with complexity sizing.

## Notes

- All test tasks (TASK-003, TASK-005, TASK-009) must pass before integration milestone completes
- TASK-010 (live validation) is the final gate before claiming feature complete
- GraphQL query pattern exists in `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1` for reference
- Preserve Get-UnacknowledgedComments unchanged to maintain backward compatibility
- Follow Skill-PowerShell-002: Functions always return arrays, never $null
