# Test Coverage Analysis: PR #453 Security Fixes

**Date**: 2025-12-26
**PR**: #453 (fix/400-pr-maintenance-visibility)
**Branch**: fix/400-pr-maintenance-visibility
**Commits Analyzed**:
- ce3ebab: fix(security): address GraphQL injection and input validation issues
- b257aea: test: remove file-based lock tests (ADR-015)

## Executive Summary

**Coverage Status**: GAPS IDENTIFIED
**Test Pass Rate**: 135/135 (100%)
**Critical Finding**: GraphQL variable injection mitigation has NO BEHAVIORAL TESTS

## Security Fixes Applied

### Fix 1: GraphQL Injection Prevention (HIGH Security)

**Files Changed**:
1. `Get-UnresolvedReviewThreads.ps1` (lines 98-118)
2. `Invoke-PRMaintenance.ps1` (lines 234-283)

**Security Pattern**: Changed from string interpolation to GraphQL variables

**Before (VULNERABLE)**:
```graphql
query {
    repository(owner: "$Owner", name: "$Repo") {
        pullRequest(number: $PR) { ... }
    }
}
```

**After (SECURE)**:
```graphql
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) { ... }
    }
}
# Passed as: -f owner="$Owner" -f name="$Repo" -F prNumber=$PR
```

**Test Coverage**: [FAIL]
- **Structural tests**: PASS (verify query contains variable declarations)
- **Behavioral tests**: MISSING (no tests verify injection is prevented)

### Fix 2: Branch Name Validation (HIGH Security)

**File Changed**: `Resolve-PRConflicts.ps1` (lines 238-248)

**Code Added**:
```powershell
if (-not (Test-SafeBranchName -BranchName $TargetBranch)) {
    $result.Message = "Rejecting PR #$PRNumber due to unsafe target branch name: $TargetBranch"
    Write-Error $result.Message
    return $result
}
```

**Test Coverage**: [PASS]
- Structural tests verify `Test-SafeBranchName` validation checks exist
- Tests cover: empty, hyphen-prefix, path traversal, control chars, git special chars, shell metacharacters
- Tests are STRUCTURAL ONLY (regex pattern verification)
- No BEHAVIORAL tests with actual malicious input

### Fix 3: File-Based Locking Removal (ADR-015 Compliance)

**File Changed**: `Invoke-PRMaintenance.ps1` (deleted Enter-ScriptLock, Exit-ScriptLock)

**Test Coverage**: [PASS]
- Tests for deleted functions removed in commit b257aea
- 19 test lines removed from Invoke-PRMaintenance.Tests.ps1

## Test Coverage Metrics

### File: Get-UnresolvedReviewThreads.ps1

| Test Type | Count | Coverage Target | Status |
|-----------|-------|-----------------|--------|
| Structural | 32 | Script syntax, params, GraphQL query structure | [PASS] |
| Behavioral | 0 | GraphQL variable injection prevention | [FAIL] |
| Integration | 0 | Live GraphQL API calls | [SKIP] |

**Critical Gaps**:
1. No test verifies that malicious `Owner` like `"; malicious code"` is properly escaped
2. No test verifies GraphQL variables prevent injection (behavioral)
3. Tests only check query CONTAINS `query($owner: String!` (structural pattern matching)

### File: Resolve-PRConflicts.ps1

| Test Type | Count | Coverage Target | Status |
|-----------|-------|-----------------|--------|
| Structural | 54 | Script syntax, security function definitions | [PASS] |
| Behavioral | 0 | Branch name validation with malicious input | [FAIL] |
| Integration | 0 | Actual git operations with validated names | [SKIP] |

**Critical Gaps**:
1. No test calls `Test-SafeBranchName` with malicious input like `"; rm -rf /"` or `../../../etc/passwd`
2. No test verifies that `TargetBranch` validation actually rejects unsafe names
3. Tests only verify regex patterns EXIST in script (line 70-96), not that they WORK

### File: Invoke-PRMaintenance.ps1

| Test Type | Count | Coverage Target | Status |
|-----------|-------|---|--------|
| Structural | 49 | Script structure, classification logic | [PASS] |
| Behavioral | 0 | GraphQL variable injection prevention | [FAIL] |
| Functional | 49 | Bot classification, conflict detection | [PASS] |

**Critical Gaps**:
1. Same GraphQL injection gap as Get-UnresolvedReviewThreads.ps1
2. No test verifies GraphQL query uses variables instead of string interpolation
3. Tests check query contains variable syntax but don't verify injection is prevented

## Gap Analysis Summary

### Critical Gaps (Security HIGH)

| Gap | Risk | Recommendation |
|-----|------|----------------|
| No GraphQL injection behavioral tests | HIGH | Add tests with malicious Owner/Repo/PR values |
| No branch name validation behavioral tests | HIGH | Add tests calling Test-SafeBranchName with attack strings |
| No integration tests for security fixes | MEDIUM | Add end-to-end tests with actual git/GraphQL operations |

### Test Coverage by Category

| Category | Tests Exist | Coverage % | Status |
|----------|-------------|------------|--------|
| Structural (syntax, patterns) | 135 | 100% | [PASS] |
| Behavioral (actual validation) | 0 | 0% | [FAIL] |
| Integration (end-to-end) | 0 | 0% | [SKIP] |
| Edge Cases (malicious input) | 0 | 0% | [FAIL] |

## Detailed Gap Findings

### Gap 1: GraphQL Injection Behavioral Tests

**Severity**: HIGH
**Affected Files**: Get-UnresolvedReviewThreads.ps1, Invoke-PRMaintenance.ps1

**Current Test Coverage**:
```posh
It 'Should query reviewThreads' {
    $ScriptContent | Should -Match 'reviewThreads\s*\(\s*first:\s*100\s*\)'
}
```

**Gap**: This only verifies the query CONTAINS the word "reviewThreads", not that variables prevent injection.

**Missing Test**:
```posh
It 'Should use GraphQL variables instead of string interpolation' {
    $ScriptContent | Should -Match 'query\(\$owner:\s*String!,\s*\$name:\s*String!,\s*\$prNumber:\s*Int!'
    $ScriptContent | Should -Match '-f\s+owner='
    $ScriptContent | Should -Match '-f\s+name='
    $ScriptContent | Should -Match '-F\s+prNumber='
}

It 'Should prevent GraphQL injection via Owner parameter' {
    # Behavioral test: Actually call function with malicious input
    Mock gh { return @{} | ConvertTo-Json }

    . $ScriptPath
    $result = Get-UnresolvedReviewThreads -Owner '"; DROP TABLE users;--' -Repo 'test' -PR 1

    # Verify gh was called with -f flag (variables), not string interpolation
    Assert-MockCalled gh -ParameterFilter {
        $args -contains '-f' -and $args -contains 'owner="' + '"; DROP TABLE users;--' + '"'
    }
}
```

### Gap 2: Branch Name Validation Behavioral Tests

**Severity**: HIGH
**Affected File**: Resolve-PRConflicts.ps1

**Current Test Coverage**:
```posh
It 'Should check for shell metacharacters in branch names' {
    $ScriptContent | Should -Match '\[.*;\&\|<>\(\)\{\}'
}
```

**Gap**: This only verifies regex pattern EXISTS in script, not that validation REJECTS malicious input.

**Missing Test**:
```posh
BeforeAll {
    . $ScriptPath  # Dot-source to load functions
}

Context 'Test-SafeBranchName - Behavioral Tests' {
    It 'Should reject branch name with semicolon (command injection)' {
        Test-SafeBranchName -BranchName 'feature;rm -rf /' | Should -Be $false
    }

    It 'Should reject branch name with path traversal' {
        Test-SafeBranchName -BranchName 'feature/../../../etc/passwd' | Should -Be $false
    }

    It 'Should reject branch name starting with hyphen (git option injection)' {
        Test-SafeBranchName -BranchName '--exec=malicious' | Should -Be $false
    }

    It 'Should accept valid branch name' {
        Test-SafeBranchName -BranchName 'feature/my-branch' | Should -Be $true
    }
}

Context 'Resolve-PRConflicts - TargetBranch Validation' {
    It 'Should reject PR with unsafe TargetBranch' {
        Mock git { }  # Mock git commands

        $result = Resolve-PRConflicts -PRNumber 123 -BranchName 'feature' -TargetBranch 'main;rm -rf /'

        $result.Success | Should -Be $false
        $result.Message | Should -Match 'unsafe target branch name'
    }
}
```

### Gap 3: Edge Case Coverage

**Severity**: MEDIUM
**Affected Files**: All modified scripts

**Missing Tests**:
1. Empty string inputs for Owner/Repo/BranchName
2. Unicode characters in branch names
3. Extremely long branch names (buffer overflow)
4. NULL bytes in GraphQL parameters
5. Newlines in branch names (multiline injection)

## Recommendations

### Immediate Actions (Priority: HIGH)

1. **Add GraphQL Injection Behavioral Tests**
   - Test Get-UnresolvedReviewThreads with malicious Owner/Repo/PR
   - Test Invoke-PRMaintenance with malicious Owner/Repo/Limit
   - Verify gh called with `-f` flag (variables), not string interpolation
   - Test with: `"; DROP TABLE"`, `' OR 1=1--`, `$(malicious command)`

2. **Add Branch Name Validation Behavioral Tests**
   - Load Resolve-PRConflicts.ps1 via dot-sourcing
   - Call Test-SafeBranchName with attack strings
   - Verify rejection of: semicolon, pipe, backtick, dollar sign, path traversal, hyphen prefix
   - Verify acceptance of valid names: `feature/my-branch`, `fix/bug-123`

3. **Add TargetBranch Validation Tests**
   - Test Resolve-PRConflicts rejects unsafe TargetBranch
   - Verify error message contains "unsafe target branch name"
   - Verify function returns Success=false

### Medium-Term Actions (Priority: MEDIUM)

4. **Add Integration Tests**
   - Mock gh GraphQL API responses
   - Verify actual git command construction
   - Test end-to-end workflow with validated inputs

5. **Add Edge Case Tests**
   - Empty strings, NULL, whitespace-only
   - Unicode characters, control characters
   - Maximum length inputs (buffer overflow check)

### Test File Locations for New Tests

```
.claude/skills/github/tests/Get-UnresolvedReviewThreads.Tests.ps1
    + Add Context 'GraphQL Injection Prevention - Behavioral Tests'

.claude/skills/merge-resolver/tests/Resolve-PRConflicts.Tests.ps1
    + Add Context 'Test-SafeBranchName - Behavioral Tests'
    + Add Context 'TargetBranch Validation - Behavioral Tests'

scripts/tests/Invoke-PRMaintenance.Tests.ps1
    + Add Context 'GraphQL Injection Prevention - Behavioral Tests'
```

## Test Execution Results

All existing tests passed:
- Resolve-PRConflicts.Tests.ps1: 54/54 [PASS]
- Get-UnresolvedReviewThreads.Tests.ps1: 32/32 [PASS]
- Invoke-PRMaintenance.Tests.ps1: 49/49 [PASS]

**Total**: 135 tests passed, 0 failed, 0 skipped

## Verdict

**Status**: [NEEDS WORK]
**Confidence**: LOW
**Rationale**: While all existing tests pass and structural coverage is 100%, there are ZERO behavioral tests for the security fixes. Tests verify that security code EXISTS but not that it WORKS. This is insufficient for security-critical changes like injection prevention.

### Risk Assessment

| Risk | Likelihood | Impact | Severity |
|------|------------|--------|----------|
| GraphQL injection undetected | MEDIUM | HIGH | HIGH |
| Branch name injection undetected | MEDIUM | HIGH | HIGH |
| Regression in security fixes | HIGH | HIGH | CRITICAL |

**Recommendation**: DO NOT MERGE until behavioral tests are added to verify:
1. GraphQL variables prevent injection
2. Test-SafeBranchName rejects malicious input
3. TargetBranch validation works correctly

## References

- ADR-015: Security validation requirements
- Commit ce3ebab: Security fix implementation
- Commit b257aea: Test removal for deleted lock functions
- Test files analyzed: 3 files, 135 tests total
