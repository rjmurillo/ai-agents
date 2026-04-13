# Test Coverage Report: Test-PRHasFailingChecks

**Date**: 2025-12-26
**Function**: Test-PRHasFailingChecks (scripts/Invoke-PRMaintenance.ps1)
**Analyst**: QA

## Executive Summary

Test suite for `Test-PRHasFailingChecks` achieves **100% line coverage** and **87.5% instruction coverage** for the function itself. All 9 tests pass. However, **5-7 critical edge cases remain untested**, including EXPECTED state handling, StatusContext ERROR state, and PSObject compatibility.

**Recommendation**: Add 5-7 tests for missing edge cases before production deployment.

## Coverage by the Numbers

| Category | Coverage | Status |
|----------|----------|--------|
| **Function Line Coverage** | 24/24 (100%) | [PASS] |
| **Function Instruction Coverage** | 28/32 (87.5%) | [PASS] |
| **Tests Passing** | 9/9 (100%) | [PASS] |
| **Edge Cases Tested** | 6/13 (46%) | [FAIL] |
| **Code Paths Tested** | 12/17 (71%) | [FAIL] |

## Test Results

```
Tests Passed: 9, Failed: 0, Skipped: 0
Execution Time: 8.04s
```

### Test Breakdown

| Test Category | Count | Status |
|---------------|-------|--------|
| Null safety guards | 3 | [PASS] |
| Rollup state detection | 3 | [PASS] |
| Individual CheckRun conclusions | 2 | [PASS] |
| StatusContext state (legacy API) | 1 | [PASS] |

## What's Tested [PASS]

1. **Null Safety** (3 tests)
   - Null commits structure
   - Empty commits.nodes array
   - Null statusCheckRollup

2. **Rollup States** (3 tests)
   - FAILURE state returns true
   - ERROR state returns true
   - SUCCESS state returns false
   - PENDING state with no failures returns false

3. **CheckRun Conclusions** (2 tests)
   - FAILURE conclusion returns true
   - Mixed SUCCESS/FAILURE returns true
   - All SUCCESS returns false

4. **StatusContext Legacy API** (1 test)
   - FAILURE state returns true

## What's Missing [FAIL]

### Priority 1: Critical Edge Cases

1. **EXPECTED state**: Valid rollup state, should return false
   - Risk: Misclassifying expected checks as failures
   - Impact: HIGH - Could trigger unnecessary PR actions

2. **StatusContext ERROR state**: Equivalent to FAILURE, should return true
   - Risk: Missing actual failures in repos using legacy status API
   - Impact: HIGH - PRs with failing checks marked as passing

3. **Mixed CheckRun + StatusContext**: Both types in same contexts array
   - Risk: Function might not correctly handle heterogeneous context types
   - Impact: MEDIUM - Common in repos transitioning from Status to Checks API

### Priority 2: High-Value Edge Cases

4. **Non-FAILURE conclusions**: ACTION_REQUIRED, CANCELLED, TIMED_OUT, STARTUP_FAILURE
   - Current behavior: Treated as passing (returns false)
   - Risk: These might indicate issues but are ignored
   - Impact: MEDIUM - Depends on team's CI/CD philosophy

5. **PSObject vs Hashtable**: Tests use hashtables, but real API returns PSObjects
   - Risk: Get-SafeProperty might behave differently
   - Impact: MEDIUM - Could cause production failures despite passing tests

6. **Case sensitivity**: States/conclusions use uppercase strings
   - Risk: If API returns lowercase, comparison might fail
   - Impact: LOW - GitHub API is consistent, but no explicit test

### Priority 3: Nice-to-Have

7. **Multiple StatusContexts with one ERROR**: Ensure iteration works correctly
8. **Empty string conclusions/states**: Validate handling of malformed data
9. **Contexts array at query limit (50 items)**: Behavior with large check suites

## Data Realism Assessment

### Realistic [PASS]
- Proper GraphQL nested structure
- Multiple commits nodes (though only [0] used)
- Multiple contexts in array format
- Both CheckRun and StatusContext types represented

### Unrealistic [WARNING]
- Tests use hashtables, not PSObjects from ConvertFrom-Json
- Simplified contexts (missing name, status, detailsUrl, timestamps)
- No checkpoint/checkSuite/app data from real CheckRuns
- No indication which checks are required vs optional

## Integration Test Gap [FAIL]

**No integration tests exist** that:
1. Mock gh api GraphQL response
2. Parse JSON to PSObjects
3. Call Get-OpenPRs
4. Pass result to Test-PRHasFailingChecks
5. Verify end-to-end behavior

This gap means tests might pass but production could fail due to:
- PSObject property access differences
- JSON parsing edge cases
- GraphQL schema changes

## Code Quality Observations

### Strengths
- Excellent null safety with Get-SafeProperty helper
- Clear separation of concerns (rollup state vs individual contexts)
- Handles both CheckRun and StatusContext types
- Comprehensive documentation

### Concerns
1. **Potential false negatives**: ACTION_REQUIRED, CANCELLED, TIMED_OUT treated as passing
2. **No required check logic**: Failed optional checks trigger true, but might not need action
3. **Magic strings**: No constants/enums for states and conclusions
4. **4 uncovered instructions**: Likely correspond to untested branches

## Recommendations

### Immediate Actions (Before Production)

1. **Add EXPECTED state test** (5 min)
   ```powershell
   It "Returns false when statusCheckRollup state is EXPECTED" {
       $pr = @{ commits = @{ nodes = @(@{ commit = @{ statusCheckRollup = @{ state = "EXPECTED"; contexts = @{ nodes = @() } } } }) } }
       Test-PRHasFailingChecks -PR $pr | Should -Be $false
   }
   ```

2. **Add StatusContext ERROR test** (5 min)
   ```powershell
   It "Returns true when StatusContext state is ERROR" {
       $pr = @{ commits = @{ nodes = @(@{ commit = @{ statusCheckRollup = @{ state = "PENDING"; contexts = @{ nodes = @(@{ state = "ERROR"; context = "ci/build" }) } } } }) } }
       Test-PRHasFailingChecks -PR $pr | Should -Be $true
   }
   ```

3. **Add mixed context type test** (10 min)
   ```powershell
   It "Returns true when StatusContext FAILURE with CheckRun SUCCESS" {
       $pr = @{ commits = @{ nodes = @(@{ commit = @{ statusCheckRollup = @{ state = "PENDING"; contexts = @{ nodes = @(@{ conclusion = "SUCCESS" }, @{ state = "FAILURE"; context = "legacy" }) } } } }) } }
       Test-PRHasFailingChecks -PR $pr | Should -Be $true
   }
   ```

### Short-Term Improvements (This Sprint)

4. **Add PSObject compatibility test** (30 min)
   - Create test using ConvertFrom-Json
   - Verify Get-SafeProperty works with both hashtables and PSObjects

5. **Document non-FAILURE conclusion behavior** (15 min)
   - Add code comment explaining why ACTION_REQUIRED etc. return false
   - Link to team decision or ADR if applicable

### Long-Term Enhancements (Next Quarter)

6. **Add integration test with mocked gh api** (2 hours)
7. **Extract state/conclusion constants** (1 hour)
8. **Investigate required check logic** (4 hours - requires GraphQL schema research)

## Test Execution Evidence

```
Pester v5.7.1
Starting discovery in 1 files.
Discovery found 48 tests in 652ms.
Running tests.

Context Test-PRHasFailingChecks Function
  [+] Returns true when statusCheckRollup state is FAILURE 106ms
  [+] Returns true when statusCheckRollup state is ERROR 82ms
  [+] Returns true when a CheckRun has FAILURE conclusion 79ms
  [+] Returns false when all checks pass 74ms
  [+] Returns false when commits is null (no check data) 69ms
  [+] Returns false when commits.nodes is empty 74ms
  [+] Returns false when statusCheckRollup is null 76ms
  [+] Handles StatusContext with state property (legacy status API) 74ms
  [+] Returns false when PENDING but no failures 93ms

Tests Passed: 48, Failed: 0, Skipped: 0
Tests completed in 8.04s

Code Coverage: 50.11% overall (191/356 lines)
Test-PRHasFailingChecks: 100% lines (24/24), 87.5% instructions (28/32)
```

## Verdict

**Status**: NEEDS WORK
**Confidence**: High
**Current State**: Tests pass, good coverage of happy paths
**Blocker**: Missing critical edge cases (EXPECTED, StatusContext ERROR, mixed types)
**Action Required**: Add 3 critical tests before production deployment (estimated 20 minutes)

---

**Full Analysis**: See `.agents/qa/test-coverage-Test-PRHasFailingChecks.md`
