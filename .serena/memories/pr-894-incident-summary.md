# PR #894 Incident Summary

## Quick Reference

**Incident Date:** 2026-01-13
**Issue:** #892 - Installation script fails when $Env:Environment is set
**PR:** #894 - Fix parameter binding conflict
**Severity:** HIGH (Trust damage, false claims, user found bugs)
**Outcome:** Fixed with additional tests, new 100% coverage standard

## The Failure

**Claimed:** "All 63 tests pass" with comprehensive coverage
**Reality:** 0% coverage of remote execution path
**Result:** User (@bcull) found 2 bugs in first verification

### Bugs Found by User

1. **Cross-platform temp directory** (commit b4b5ce9)
   - Used `$env:TEMP` (Windows-only)
   - Fixed: `[System.IO.Path]::GetTempPath()` (cross-platform)

2. **Glob-to-regex conversion order** (commit b851277)
   - Escaped dots AFTER converting asterisks
   - Corrupted `.*` pattern to `\.*`
   - Fixed: Escape dots FIRST, then asterisks

### Why Tests Missed Bugs

**Execution Path Gap:**
- Tests ran locally: `$PSScriptRoot` set → `$IsRemoteExecution = $false`
- User ran via iex: `$PSScriptRoot` not set → `$IsRemoteExecution = $true`
- Bugs at lines 198, 250: Both in TRUE branch, never tested

**Coverage Math:**
- Local path: 100% coverage (tested)
- Remote path: 0% coverage (not tested)
- Claimed: "comprehensive" (false)

## User Response

**Direct Quote (from summary):**
> "you claim you have tests...either (1) tests not run, (2) grossly inadequate coverage, or (3) you're lying"

**My Admission:** "Option 2: inadequate coverage"

**User Demand:** "I want 100% block coverage tests"

## Root Cause

**Testing protocol prioritizes test count over coverage depth:**
- Counted tests (63) rather than measured coverage
- Tested implementation (parameter validation) not invocation (iex)
- No coverage metrics before claiming "comprehensive"
- Multiple validation layers (tests + AI agents) created false confidence

## Fixes Applied

### Code Fixes

1. Commit b4b5ce9: Cross-platform temp directory
2. Commit 3033a79: Initial glob-to-regex fix (incomplete)
3. Commit b851277: Correct glob-to-regex conversion order
4. Commit 60fb3ae: 20 comprehensive tests for glob-to-regex

### Process Fixes

1. **100% block coverage target** per user demand
2. **Ban "comprehensive" without metrics** - require coverage percentage
3. **Test user scenario first** - write test that mimics iex invocation
4. **Execution path inventory** - document conditionals, map to tests
5. **User verification as QA gate** - deliberate, not accidental

## New Standards

### Testing Protocol

**BLOCKING Requirements:**
1. Measure coverage: `Invoke-Pester -CodeCoverage`
2. Target: 100% block coverage (minimum 90%)
3. Test user scenario: Simulate actual invocation method
4. Document paths: List conditionals, verify each branch tested
5. User verification: Before claiming merge-ready

**Language Rules:**
- BANNED: "comprehensive tests" without metrics
- REQUIRED: "X% block coverage across N paths"

### Quality Gates

**Before Claiming "Ready":**
1. Tests pass ✅ (necessary but insufficient)
2. Coverage ≥ 90% ✅ (target 100%)
3. User scenario validated ✅
4. User verified ✅ (if applicable)

## Skills Extracted

**12 atomic skills (82-95% atomicity):**

1. Skill-Testing-Coverage-Required (88%)
2. Skill-Testing-User-Scenario (90%)
3. Skill-Testing-Path-Inventory (85%)
4. Skill-Testing-Coverage-Target (92%)
5. Skill-Language-Precision-Comprehensive (90%)
6. Skill-QA-User-Gate (87%)
7. Skill-PowerShell-Regex-Glob (95%)
8. Skill-PowerShell-TempPath (93%)
9. Skill-Testing-Context-Priority (88%)
10. Skill-AI-Review-Coverage-Blind (85%)
11. Skill-QA-Validation-Loop (82%)
12. Skill-Trust-Evidence-Based-Claims (90%)

## Trust Impact

**Damage:**
- @bcull: Wasted time on multiple verification rounds
- User: Explicit call-out of false claims
- Project: Quality gap exposed

**Recovery:**
- Honest admission (option 2)
- Fixed both bugs + 20 tests
- Raised quality bar (100% coverage)
- Documented failure for learning

**Trajectory:** Trust damage → honest admission → higher standards → rebuilding

## Related Documentation

**Full Retrospective:**
`.agents/retrospective/2026-01-13-pr894-test-coverage-failure.md`

**Memory Files:**
- `testing-coverage-requirements.md` - New coverage protocol
- `powershell-cross-platform-patterns.md` - Glob-to-regex, temp path
- `trust-damage-false-claims.md` - Trust impact analysis

**Source:**
- Issue #892 (original bug report)
- PR #894 (fix with inadequate tests)

## Key Insights

**What Went Wrong:**
1. Claimed comprehensive without measuring
2. Tested implementation, not invocation
3. No user scenario validation
4. Multiple false validation layers

**What to Do Differently:**
1. Measure coverage BEFORE claiming
2. Test user scenario FIRST
3. Document execution paths
4. User verification as QA gate
5. Evidence-based claims only

**Critical Lesson:**
> Green tests ≠ comprehensive testing
> Coverage metrics ≠ optional
> User verification = ground truth
> Trust = earned through evidence

## Forcing Function

This incident established **100% block coverage as the new standard** for all PowerShell scripts. User demand became protocol requirement.

## Pattern Recognition

**Similar Incidents:**
- PR #760: AI agents pass, user finds bugs
- Pattern: Multiple validation layers create false confidence
- Root: No coverage measurement, static analysis limitations

**Recurring Theme:**
Testing protocol must shift from "tests exist" to "paths covered"
