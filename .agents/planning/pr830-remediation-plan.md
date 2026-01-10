# PR 830 Remediation Plan

**Date**: 2026-01-08  
**PR**: #830 - Session protocol validation refactoring  
**Status**: ACTIVE  
**Priority**: P0 - BLOCKING

## Problem Statement

PR 830 has 29/55 tests failing due to contract violations in SessionValidation.psm1. Functions return extra keys beyond the standardized 4-key contract expected by tests.

**Root Cause**: Implicit contract not maintained during refactoring.

## Strategy

**Option C (Hybrid)**: Restore standardized contract immediately, add enhanced diagnostics via `-Detailed` switch in follow-up.

## Phase 1: Immediate Stabilization (THIS SESSION)

**Objective**: Make all tests pass by restoring standardized 4-key contract.

### Tasks

#### Task 1.1: Identify All Contract Violations
**Status**: In Progress

Scan SessionValidation.psm1 for all return statements that include non-standard keys.

**Non-Standard Keys to Remove**:
- `Passed` (redundant with `IsValid`)
- `Level` (internal metadata)
- `Issues` (redundant with `Errors`)
- `Details` (diagnostic information)
- `ErrorMessage` (redundant with `Errors`)
- `MemoriesFound` (diagnostic information)
- `MissingMemories` (diagnostic information)
- `Sections` (diagnostic information)

**Standard Keys to Keep**:
- `IsValid` (boolean)
- `Errors` (string array)
- `Warnings` (string array)
- `FixableIssues` (hashtable array)

#### Task 1.2: Fix Test-MemoryEvidence Function
**Status**: Not Started

Lines ~195-320 in SessionValidation.psm1

**Current**: Returns 11 keys including `Passed`, `Level`, `Issues`, `Details`, `ErrorMessage`, `MemoriesFound`, `MissingMemories`

**Target**: Return only `@{ IsValid; Errors; Warnings; FixableIssues }`

**Changes**:
- Remove `Passed`, `Level`, `ErrorMessage` from all return statements
- Move `MemoriesFound`, `MissingMemories` into `FixableIssues[].Details` if needed
- Remove `Details` hashtable entirely
- Keep diagnostic info in `Errors` array as strings

#### Task 1.3: Fix Test-ProtocolComplianceSection Function
**Status**: Not Started

Lines ~350-370

**Changes**: Remove extra keys, keep standard 4.

#### Task 1.4: Fix Test-MustRequirements Function
**Status**: Not Started

Lines ~380-450

**Current**: Returns `Details`, `Passed`, `Level`, `Issues`

**Target**: Return only standard 4 keys

#### Task 1.5: Fix Test-MustNotRequirements Function
**Status**: Not Started

Similar pattern to Test-MustRequirements

#### Task 1.6: Fix Test-HandoffUpdated Function
**Status**: Not Started

Lines ~500-600

**Changes**: Remove `Passed`, `Level`, `Issues`

#### Task 1.7: Fix Test-ShouldRequirements Function
**Status**: Not Started

Lines ~600-640

**Changes**: Remove `Details`, `Passed`, `Level`, `Issues`

#### Task 1.8: Fix Test-GitCommitEvidence Function
**Status**: Not Started

Lines ~640-680

**Changes**: Remove extra keys

#### Task 1.9: Fix Test-SessionLogCompleteness Function
**Status**: Not Started

Lines ~680-720

**Current**: Returns `Sections` key

**Changes**: Remove `Sections`, incorporate into `Errors` or `Warnings` as needed

### Verification Checklist

- [ ] All Test-* functions return exactly 4 keys: `IsValid`, `Errors`, `Warnings`, `FixableIssues`
- [ ] Run `Invoke-Pester -Path './scripts/modules/SessionValidation.Tests.ps1'` locally
- [ ] Expect 55/55 tests passing
- [ ] Run `Invoke-Pester -Path './scripts/tests/Validate-SessionProtocol.Tests.ps1'` locally
- [ ] Expect 29/29 tests passing (or whatever the correct count is)
- [ ] Commit changes with descriptive message
- [ ] Push and verify CI goes green
- [ ] Update PR status with fix summary

## Phase 2: Contract Documentation (FOLLOW-UP PR)

**Objective**: Prevent future implicit contract violations.

### Tasks

- [ ] Add `.OUTPUTS` CBH section to all Test-* functions
- [ ] Add `[OutputType([hashtable])]` attribute to all Test-* functions
- [ ] Create `scripts/modules/CONTRACT.md` specification
- [ ] Update `Assert-StandardContract` test helper to reference CONTRACT.md
- [ ] Add contract validation to Validate-Consistency.ps1

## Phase 3: Enhanced Diagnostics (FOLLOW-UP PR)

**Objective**: Add detailed diagnostics without breaking contract.

### Tasks

- [ ] Add `-Detailed` switch parameter to validation functions
- [ ] Return extended keys only when `-Detailed` specified
- [ ] Update Validate-SessionProtocol.ps1 to use `-Detailed`
- [ ] Add Pester tests for both standard and detailed contracts
- [ ] Document usage patterns in function CBH

## Phase 4: Process Hardening (FOLLOW-UP PR)

**Objective**: Prevent recurrence through automation.

### Tasks

- [ ] Add Pester test run to `.githooks/pre-commit`
- [ ] Document test-before-commit requirement in SESSION-PROTOCOL.md
- [ ] Create CONTRACT-TESTING.md guide
- [ ] Add contract violation detection to Validate-Consistency.ps1
- [ ] Update agent instructions to emphasize contract testing

## Success Criteria

**Phase 1 (BLOCKING)**:
- ✅ All Pester tests pass (100% pass rate)
- ✅ All CI checks green on PR 830
- ✅ No contract violations detected

**Phase 2-4 (Quality)**:
- ✅ All functions have explicit contract documentation
- ✅ Enhanced diagnostics available via opt-in
- ✅ Automated enforcement prevents future violations

## Timeline

- **Phase 1**: This session (immediate)
- **Phase 2**: Follow-up PR (1-2 days)
- **Phase 3**: Follow-up PR (3-5 days)
- **Phase 4**: Follow-up PR (1 week)

## Risks

| Risk | Mitigation |
|------|------------|
| Breaking callers expecting enhanced keys | Verify no callers exist outside test suite |
| Tests still fail after fix | Run tests incrementally, fix function-by-function |
| Losing valuable diagnostic information | Preserve in Errors array, add -Detailed switch in Phase 3 |

## Notes

- **DO NOT** add new functionality in Phase 1 - only restore contract
- **DO** verify tests pass after each function fix
- **DO** run full test suite before commit
- **DO NOT** push until local tests are 100% green

---

**Status**: Ready for execution  
**Owner**: Agent  
**Next Action**: Start Task 1.1 - Identify all contract violations
