# Plan Critique: PR Maintenance Authority Enhancement Tasks

**Review Date**: 2025-12-26
**Reviewed By**: critic agent
**Plan Document**: `.agents/planning/tasks-pr-maintenance-authority.md`

## Verdict
**NEEDS REVISION**

## Summary
Task prompts contain critical self-containment issues. 11 of 17 tasks require revision before execution. Primary issues: vague location references requiring cross-task context, incomplete test structure documentation, missing absolute file paths, and reliance on prior conversation state that amnesiac agents cannot access.

## Strengths
- Tasks 1.1, 1.2: Excellent - specific line numbers, complete code, zero ambiguity
- Task 3.1: Complete function implementation with no placeholders or missing context
- Task 4.1: Clear replacement logic with full code block showing all branches
- Task 5.5: Only test prompt with complete structure and clear regression purpose
- All acceptance criteria are measurable and verifiable
- Dependency tracking is accurate and explicit
- Code blocks are syntactically complete (no `# existing code` placeholders)

## Issues Found

### Critical (Must Fix)

- [ ] **Task 1.3**: Vague location references ("after Task 1.2", "around line 1291")
  - **Location**: Lines 149-169 of tasks document
  - **Issue**: Agent must hunt for duplicate call. Ambiguous "Remove or comment out" instruction lacks decisiveness.
  - **Evidence**: Prompt says "Remove or comment out any duplicate Get-UnacknowledgedComments call later in the block" without specifying exact line
  - **Recommendation**: Provide BEFORE/AFTER code blocks with exact search pattern for the duplicate call

- [ ] **Task 2.2**: Missing case-insensitivity flag in regex pattern
  - **Location**: Lines 213-260
  - **Issue**: Pattern `-match '(coderabbitai|cursor\[bot\]|gemini-code-assist)'` uses default case-sensitive matching
  - **Impact**: Will miss bot comments with different casing (CodeRabbitAI vs coderabbitai)
  - **Recommendation**: Add `(?i)` flag or use `-imatch` operator

- [ ] **Task 2.2**: Vague placement instruction
  - **Location**: Lines 213-260
  - **Issue**: Says "add comment collection after the copilot detection block (Task 2.1)" without absolute line reference
  - **Impact**: Agent must search for Task 2.1 code first
  - **Recommendation**: Specify "approximately line 1268, AFTER $isCopilotPR detection, BEFORE action determination"

- [ ] **Task 3.2**: Incomplete results initialization context
  - **Location**: Lines 328-369
  - **Issue**: Says "Add $results.SynthesisPosted = 0 to the results initialization if not present" without specifying WHERE initialization is
  - **Impact**: Agent doesn't know location or structure of results initialization block
  - **Recommendation**: Provide exact search pattern ("Locate `$results = @{`") and line range estimate

- [ ] **Tasks 5.1, 5.2, 5.3, 5.4, 5.6**: Assume "Process-SinglePR" function exists
  - **Location**: Lines 442-486, 488-534, 536-583, 586-634, 682-726
  - **Issue**: All tests call `Process-SinglePR` without verification that this function exists
  - **Impact**: Tests will fail if function doesn't exist or has different signature
  - **Recommendation**: Verify function exists OR document actual invocation pattern (script execution vs. function call)

- [ ] **Task 5.7**: Uses real PR numbers without state validation
  - **Location**: Lines 728-788
  - **Issue**: Tests hardcode PRs #365, #353, #301, #255, #247, #235 which may be closed or deleted
  - **Impact**: Integration tests will fail unpredictably as PR states change
  - **Recommendation**: Add PR state checks with skip conditions OR use mock data instead of live PRs

- [ ] **Task 5.7**: Creates new file without absolute path
  - **Location**: Lines 728-788
  - **Issue**: Says "Create tests/Integration-PRMaintenance.Tests.ps1" without `/home/richard/ai-agents/` prefix
  - **Impact**: Minor - agent can infer, but violates self-containment principle
  - **Recommendation**: Use absolute path `/home/richard/ai-agents/tests/Integration-PRMaintenance.Tests.ps1`

- [ ] **Task 6.1**: Line number references without structural context
  - **Location**: Lines 798-845
  - **Issue**: Says "ADD to Activation Triggers table (around line 133)" without showing table structure
  - **Impact**: Agent must search entire file to find table, then infer row format
  - **Recommendation**: Provide table header format and search pattern (e.g., "Search for `| **Trigger** |`")

- [ ] **Task 6.2**: No file existence verification
  - **Location**: Lines 847-891
  - **Issue**: Assumes `.agents/memories/pr-changes-requested-semantics.md` exists without check
  - **Impact**: If file doesn't exist, agent has no guidance on file creation
  - **Recommendation**: Add conditional: "If file exists, add AFTER section X. If not, create new file with content..."

### Important (Should Fix)

- [ ] **Consistency**: Only 3 of 17 tasks provide specific line numbers with complete code
  - **Issue**: Tasks 1.1, 1.2, 4.1 have exact line numbers. All others use relative references ("after Task X")
  - **Impact**: Execution time variance - some tasks complete in seconds, others require exploration
  - **Recommendation**: Standardize on format: "File: X, Line: Y (or search pattern: Z), Action: REPLACE/INSERT"

- [ ] **Test Documentation**: No explanation of existing test patterns
  - **Location**: All Phase 5 tasks
  - **Issue**: Says "Adjust mocking approach to match existing test patterns in the file" without documenting patterns
  - **Impact**: Agent must read entire test file to infer patterns (wastes cycles)
  - **Recommendation**: Add "Test File Structure Note" section documenting Describe blocks, mocking style, and invocation pattern

### Minor (Consider)

- [ ] **Verification Steps**: Some tasks lack explicit verification instructions
  - **Example**: Task 3.2 says "Synthesis only triggers once per PR per maintenance run" but doesn't specify how to verify
  - **Impact**: Minor - acceptance criteria cover verification, but explicit steps would help
  - **Recommendation**: Add "Verify: ..." step showing how to confirm correctness (search patterns, test commands)

## Questions for Planner

1. **Test Structure**: Does "Process-SinglePR" function exist in current codebase? If not, what is the actual invocation pattern for tests?
2. **Integration Test PRs**: Are PRs #365, #353, #301, #255, #247, #235 still open and in expected states? Should tests use dynamic PR discovery instead of hardcoded numbers?
3. **File Paths**: Should all prompts include absolute file paths (/home/richard/ai-agents/...) to eliminate ambiguity?
4. **Results Initialization**: What is the exact structure and location of the $results initialization block referenced in Task 3.2? (Provide line number or search pattern)
5. **Test File Structure**: What are the existing Describe blocks and mocking patterns in tests/Invoke-PRMaintenance.Tests.ps1?

## Recommendations

### 1. Revise Task 1.3 (Deduplication Refactor)
**Current Issue**: Vague location, ambiguous action

**Proposed Revision**:
```text
In scripts/Invoke-PRMaintenance.ps1, locate TWO calls to Get-UnacknowledgedComments within the $isAgentControlledBot block:

1. The FIRST call (added by Task 1.2, approximately line 1270)
2. The SECOND call (original code, approximately line 1291)

ACTION: Remove the SECOND call at line 1291 and reuse the $unacked variable from the first call.

SEARCH PATTERN: "Get-UnacknowledgedComments -Owner"

BEFORE (line ~1291):
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
foreach ($comment in $unacked) {
    $acked = Add-CommentReaction ...
}

AFTER:
# Reuse $unacked from earlier (line ~1270)
foreach ($comment in $unacked) {
    $acked = Add-CommentReaction ...
}

VERIFY: Search for "Get-UnacknowledgedComments" in the $isAgentControlledBot block - should appear exactly once.
```

### 2. Revise Task 2.2 (Copilot Comment Collection)
**Current Issue**: Missing case-insensitivity, vague placement

**Proposed Revision**: Add `(?i)` flag to regex, specify "approximately line 1268, AFTER $isCopilotPR detection, BEFORE action determination"

### 3. Revise Task 3.2 (Synthesis Posting)
**Current Issue**: Results initialization location unknown

**Proposed Revision**: Add STEP 1 with search pattern: "Locate `$results = @{` (typically around line 1200-1250)"

### 4. Revise Tasks 5.1-5.6 (Unit Tests)
**Current Issue**: Assumes Process-SinglePR exists

**Action Required**:
1. Read `/home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1`
2. Document actual test invocation pattern
3. Update all test prompts to use verified pattern

**Proposed Addition to Each Test**:
```text
NOTE: If tests/Invoke-PRMaintenance.Tests.ps1 does not exist, create it with:
- Pester framework BeforeAll block
- Describe 'Invoke-PRMaintenance' block
- Standard mocking pattern using Mock cmdlet

Invocation pattern: [DOCUMENT ACTUAL PATTERN FROM CODEBASE]
```

### 5. Revise Task 5.7 (Integration Tests)
**Current Issue**: Hardcoded PR numbers, no state handling

**Proposed Revision**: Add skip conditions for closed PRs, use absolute path

### 6. Revise Tasks 6.1, 6.2 (Documentation)
**Current Issue**: No file structure context

**Proposed Revision**: Add search patterns, file existence checks, and structural context (table headers, section hierarchy)

### 7. Global Standardization
**Action**: Convert ALL tasks to format:
```text
File: [absolute path]
Location: Line X (or search pattern: "Y")
Action: REPLACE/INSERT/DELETE
Code: [complete block with BEFORE/AFTER if replacing]
Verify: [how to confirm correctness]
```

## Approval Conditions

### Before Implementation Can Begin:

1. [x] **Task 1.3** revised with exact search pattern for duplicate call
2. [x] **Task 2.2** revised with case-insensitive regex and specific line number
3. [x] **Task 3.2** revised with results initialization search pattern
4. [x] **Tasks 5.1-5.6** revised after verifying test structure (read existing test file)
5. [x] **Task 5.7** revised with absolute path and PR state handling
6. [x] **Tasks 6.1, 6.2** revised with file existence checks and search patterns
7. [x] **All tasks** use absolute file paths (no relative references)
8. [x] **All location references** include search patterns for amnesiac agents

## Impact Analysis Review

Not applicable - no impact analysis document provided with planning artifacts.

## Revision Checklist

- [ ] Read existing test file to document actual invocation pattern
- [ ] Read existing protocol documentation to verify insertion points
- [ ] Verify $results initialization structure and location
- [ ] Update all 11 flagged tasks with specific search patterns
- [ ] Replace all "after Task X" references with absolute locations
- [ ] Add file existence checks to documentation tasks
- [ ] Replace hardcoded PR numbers with dynamic discovery or mocks
- [ ] Standardize all tasks to: File → Location → Action → Code → Verify format

## Notes

1. **Strong Foundation**: Acceptance criteria are excellent - measurable, specific, traceable to PRD
2. **Dependency Graph**: Accurate and helpful for understanding execution order
3. **Code Quality**: No placeholders like `# existing code` or `@{...}` - all code blocks are complete
4. **Main Issue**: Location references optimized for sequential human reading, not amnesiac agent execution
5. **Severity**: 11/17 tasks need revision - this is a planning iteration issue, not a fundamental design flaw

## Recommended Next Steps

1. **Planner** reads test file and documents actual structure
2. **Planner** reads protocol documentation and verifies line numbers
3. **Planner** revises 11 tasks with specific search patterns
4. **Critic** re-reviews revised tasks
5. **Implementer** executes tasks sequentially

---

**Plan Status**: NEEDS ITERATION
**Recommendation**: Route to planner with this critique for revision before implementation.
