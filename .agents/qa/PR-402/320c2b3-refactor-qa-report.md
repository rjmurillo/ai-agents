# QA Report: PR Maintenance Refactoring

**Commit**: 320c2b3
**Date**: 2025-12-26
**QA Reviewer**: qa agent
**Verdict**: CRITICAL_FAIL

## Objective

Review PR maintenance refactoring commit 320c2b3 that extracted ~1270 lines from monolithic Invoke-PRMaintenance.ps1 into separate skill modules.

**Feature**: PR maintenance script modularization
**Scope**: 8 files modified (1 main script + 3 new skill scripts + 1 workflow + 3 docs)
**Acceptance Criteria**: Tests exist for all extracted functions, code quality gates met, no regression in PR maintenance functionality

## Approach

**Test Types**: Unit tests (Pester 5.x)
**Environment**: Local development
**Data Strategy**: Mocked GitHub API responses, fixtures for PR #365 equivalent data

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tests Run | 34 | - | [PASS] |
| Passed | 34 | - | [PASS] |
| Failed | 0 | 0 | [PASS] |
| Skipped | 0 | - | - |
| Line Coverage | UNKNOWN | 80% | [FAIL] |
| Branch Coverage | UNKNOWN | 70% | [FAIL] |
| Execution Time | 7.25s | <30s | [PASS] |

### Test Results by Category

**Extracted Functions (New Code)**:

| Test | Category | Status | Notes |
|------|----------|--------|-------|
| Get-UnresolvedReviewThreads (165 lines) | Unit | [FAIL] | ZERO tests exist |
| Get-UnaddressedComments (224 lines) | Unit | [FAIL] | ZERO tests exist |
| Resolve-PRConflicts (484 lines) | Unit | [FAIL] | ZERO tests exist |
| Test-SafeBranchName | Unit | [FAIL] | ZERO tests exist |
| Get-SafeWorktreePath | Unit | [FAIL] | ZERO tests exist |
| Test-IsAutoResolvable | Unit | [FAIL] | ZERO tests exist |

**Existing Functions (Retained)**:

| Test | Category | Status | Notes |
|------|----------|--------|-------|
| Invoke-PRMaintenance classification | Unit | [PASS] | 34 tests pass |
| Get-BotAuthorInfo | Unit | [PASS] | 5 tests exist |
| Test-IsBotReviewer | Unit | [PASS] | 4 tests exist |
| Get-DerivativePRs | Unit | [PASS] | 2 tests exist |
| Rate limit safety | Unit | [PASS] | 3 tests exist |

## Discussion

### Critical Violations

**ZERO TESTS FOR NEW CODE**

The refactoring extracted 873 lines of new production code across 3 scripts:

1. **Get-UnresolvedReviewThreads.ps1** (165 lines)
   - GraphQL query parsing
   - Thread filtering logic
   - Error handling for API failures
   - JSON response validation
   - **Tests**: 0 (REMOVED during refactor)

2. **Get-UnaddressedComments.ps1** (224 lines)
   - Lifecycle state detection (NEW/ACKNOWLEDGED/REPLIED)
   - Dot-sourcing of sibling script
   - Fallback logic when thread lookup fails
   - Comment filtering with eyes reactions
   - **Tests**: 0 (REMOVED during refactor)

3. **Resolve-PRConflicts.ps1** (484 lines)
   - Branch name validation (command injection prevention)
   - Worktree path validation (path traversal prevention)
   - GitHub Actions runner detection
   - Auto-resolution logic for HANDOFF.md conflicts
   - Git worktree lifecycle management
   - **Tests**: 0

**Evidence**:

```bash
# Tests were ADDED in commit ee45485 (387 lines of tests)
git show ee45485 --stat
# Output: scripts/tests/Invoke-PRMaintenance.Tests.ps1 | 387 ++++++

# Tests were REMOVED in commit 320c2b3 (2572 lines deleted, 213 added = -2359 net)
git diff --stat ee45485 320c2b3 -- scripts/tests/Invoke-PRMaintenance.Tests.ps1
# Output: 213 insertions(+), 2572 deletions(-)

# Grep for removed tests shows:
git diff 320c2b3^1 320c2b3 -- scripts/tests/Invoke-PRMaintenance.Tests.ps1 | grep "^-.*Get-Unresolved\|^-.*Get-Unaddressed"
# Output shows:
# - Context "Get-UnresolvedReviewThreads Function" (entire section removed)
# - Context "Get-UnaddressedComments Function" (entire section removed)
# Multiple test cases calling these functions removed
```

**No test files created for extracted code**:

```bash
# No tests in github skill for new functions
ls -la .claude/skills/github/tests/
# Shows: Get-PRContext.Tests.ps1, GitHubHelpers.Tests.ps1, etc. (NO Get-Unresolved*, NO Get-Unaddressed*)

# No tests directory for merge-resolver skill
ls -la .claude/skills/merge-resolver/tests/
# Output: No such file or directory
```

### Code Quality Violations

**Function Length Violations**:

| Function | File | Lines | Threshold | Status |
|----------|------|-------|-----------|--------|
| Resolve-PRConflicts | Resolve-PRConflicts.ps1:219 | 227 | 100 (FAIL) / 50 (target) | [FAIL] |
| Get-UnaddressedComments | Get-UnaddressedComments.ps1:130 | 70 | 50 | [WARN] |
| Get-UnresolvedReviewThreads | Get-UnresolvedReviewThreads.ps1:82 | 59 | 50 | [WARN] |

**Security Code Without Tests**:

The following security-critical validation logic has ZERO tests:

1. **Test-SafeBranchName** (.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1:88-132)
   - Prevents command injection via branch names
   - Validates against: path traversal, control characters, shell metacharacters, git special chars
   - **Tests**: 0
   - **Risk**: HIGH (security validation logic must be exhaustively tested)

2. **Get-SafeWorktreePath** (.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1:141-170)
   - Prevents path traversal attacks
   - Validates PR number, resolves absolute paths, checks containment
   - **Tests**: 0
   - **Risk**: HIGH (security validation logic must be exhaustively tested)

### Risk Areas

| Area | Risk Level | Rationale |
|------|------------|-----------|
| Resolve-PRConflicts | HIGH | 484 lines handling git operations, worktrees, conflict resolution with ZERO tests |
| Security validators | HIGH | Command injection + path traversal prevention with ZERO tests |
| Get-UnaddressedComments | HIGH | Complex lifecycle state detection (NEW/ACKNOWLEDGED/REPLIED) with ZERO tests |
| Get-UnresolvedReviewThreads | MEDIUM | GraphQL query parsing with ZERO tests (simpler logic than others) |
| Invoke-PRMaintenance | LOW | 34 passing tests, logic simplified to discovery/classification only |

### Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| All extracted functions | Tests existed in ee45485, removed in 320c2b3 | P0 (BLOCKING) |
| Security validation logic | No tests created for Test-SafeBranchName, Get-SafeWorktreePath | P0 (BLOCKING) |
| Error handling paths | GraphQL failures, worktree errors, merge failures | P0 (BLOCKING) |
| Edge cases | Empty arrays, null responses, API failures | P0 (BLOCKING) |
| Lifecycle state transitions | NEW -> ACKNOWLEDGED -> REPLIED -> RESOLVED | P0 (BLOCKING) |

### Flaky Tests

None identified. All 34 tests pass deterministically.

## Recommendations

### BLOCKING (Must Fix Before Merge)

1. **Restore or recreate tests for Get-UnresolvedReviewThreads**
   - Restore 9 tests from commit ee45485 OR
   - Create new test file at .claude/skills/github/tests/Get-UnresolvedReviewThreads.Tests.ps1
   - Coverage: GraphQL query parsing, thread filtering, error handling, empty/null responses
   - **Evidence**: git show ee45485:scripts/tests/Invoke-PRMaintenance.Tests.ps1 (lines 249-336 contain 9 tests)

2. **Restore or recreate tests for Get-UnaddressedComments**
   - Restore 13 tests from commit ee45485 OR
   - Create new test file at .claude/skills/github/tests/Get-UnaddressedComments.Tests.ps1
   - Coverage: NEW/ACKNOWLEDGED/REPLIED states, thread resolution integration, fallback logic
   - **Evidence**: git show ee45485:scripts/tests/Invoke-PRMaintenance.Tests.ps1 (lines 338-472 contain 13 tests)

3. **Create tests for Resolve-PRConflicts**
   - Create .claude/skills/merge-resolver/tests/Resolve-PRConflicts.Tests.ps1
   - Minimum coverage:
     - Test-SafeBranchName: 8+ tests for all validation rules
     - Get-SafeWorktreePath: 5+ tests for path traversal prevention
     - Test-IsAutoResolvable: 3+ tests for file pattern matching
     - Resolve-PRConflicts: 10+ tests for GitHub runner mode, worktree mode, conflict scenarios
   - **Rationale**: Security validation + complex git operations = HIGH risk without tests

4. **Refactor Resolve-PRConflicts function**
   - Current: 227 lines (exceeds 100-line FAIL threshold)
   - Target: Split into sub-functions (Resolve-PRConflictsInRunner, Resolve-PRConflictsInWorktree)
   - **Evidence**: .claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1:219-446

### HIGH Priority (Should Fix)

5. **Measure actual code coverage**
   - Run: `pwsh -Command "Invoke-Pester -CodeCoverage @('scripts/Invoke-PRMaintenance.ps1', '.claude/skills/**/*.ps1') -Output Detailed"`
   - Target: 80% line coverage, 70% branch coverage
   - Document gaps in QA report

6. **Add integration tests**
   - Test end-to-end workflow: Invoke-PRMaintenance -> calls Get-Unresolved* -> outputs JSON
   - Test skill script dot-sourcing: Get-UnaddressedComments sources Get-UnresolvedReviewThreads
   - **Rationale**: Unit tests exist for individual functions, but integration may break

## Verdict

**Status**: CRITICAL_FAIL
**Confidence**: HIGH
**Rationale**: 873 lines of new production code (including security validation logic) have ZERO tests. Tests existed in commit ee45485 and were removed during refactor to 320c2b3 without being relocated to skill-specific test files.

### CRITICAL_FAIL Criteria Met

| Condition | Met? | Evidence |
|-----------|------|----------|
| Zero tests for new functionality (>10 lines) | YES | 873 lines across 3 new scripts, 0 tests |
| Untested error handling for I/O, network, file operations | YES | GraphQL API calls, git operations, worktree management |
| New code with user input but no validation tests | YES | Test-SafeBranchName, Get-SafeWorktreePath have 0 tests |
| Functions over 100 lines with no tests | YES | Resolve-PRConflicts (227 lines, 0 tests) |

## Evidence

**Tests found**: 34 for Invoke-PRMaintenance.ps1 orchestration logic
**Tests missing**: ALL tests for 3 extracted skill scripts (Get-UnresolvedReviewThreads, Get-UnaddressedComments, Resolve-PRConflicts)

**Edge cases**: NONE covered for new code (would need to verify: empty arrays, null responses, API failures, invalid inputs, concurrent access)

**Error handling**: UNTESTED for all new code (GraphQL failures, git command failures, worktree errors, path validation failures)

**Blocking issues**: 3
1. Zero tests for Get-UnresolvedReviewThreads (165 lines)
2. Zero tests for Get-UnaddressedComments (224 lines)
3. Zero tests for Resolve-PRConflicts (484 lines)

**Security risk**: HIGH - Command injection prevention (Test-SafeBranchName) and path traversal prevention (Get-SafeWorktreePath) have no tests

---

## Commit Message Claim vs Reality

**Claim**: "Tests: 34 pass, 0 fail"

**Reality**:
- TRUE: 34 tests pass for Invoke-PRMaintenance.ps1
- MISLEADING: Implies test coverage is adequate
- OMITS: Removal of 2572 test lines including all tests for extracted functions
- OMITS: Zero tests for 873 lines of new skill scripts

**Recommendation**: Commit message should disclose test removal: "Tests: 34 pass for main script, 0 tests for 3 extracted skills (TODO: restore 22 tests from ee45485)"
