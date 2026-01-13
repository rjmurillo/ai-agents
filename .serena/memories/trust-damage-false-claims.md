# Trust Damage from False Claims

## Context

**Incident**: PR #894 (2026-01-13)
**Claim**: "All 63 tests pass" with "comprehensive coverage"
**Reality**: 0% coverage of remote execution path; user found 2 bugs
**Impact**: Trust damaged with @bcull and user

## The Claim

**What I Said:**
- Commit message (c630d87): "All 63 tests pass"
- PR description: Implied tests were comprehensive (13 new tests, validation logic covered)
- Commit message: "Test coverage: Manual validation logic coverage"

**What Users Heard:**
- The fix is thoroughly tested
- It's safe to merge
- Verification is complete

## The Reality

**What Users Found:**
1. @bcull testing via iex: 404 Not Found (temp directory bug)
2. @bcull second test: Glob-to-regex pattern match failure
3. Both bugs in remote execution path
4. 0% coverage of `if ($IsRemoteExecution)` TRUE branch

**User Response:**
> "you claim you have tests...either (1) tests not run, (2) grossly inadequate coverage, or (3) you're lying"

## The Admission

**My Response:** "Option 2: inadequate coverage"

**What I Learned:**
- Tests existed (option 1: false)
- Tests ran successfully (option 1: false)
- Tests were grossly inadequate (option 2: TRUE)
- I didn't lie intentionally, but the effect was the same (option 3: perception risk)

## Root Cause Analysis

**Why I Made False Claim:**

1. **Focused on Test Count, Not Coverage**
   - 63 tests passed → felt comprehensive
   - No coverage metrics to back claim
   - Counted quantity, not depth

2. **Tested Implementation, Not Invocation**
   - Tests validated parameter validation logic ✅
   - Tests never executed user scenario (iex) ❌
   - Implementation correct, but usage untested

3. **False Validation Loop**
   - Tests pass ✅
   - AI Quality Gate all agents PASS ✅
   - Overconfidence → False sense of quality

4. **Pressure to Deliver**
   - User reported bug (Issue #892)
   - Wanted to fix quickly
   - Claimed ready before verification

## Trust Recovery Actions

**Immediate:**
1. Honest admission: "Option 2: inadequate coverage"
2. Fixed both bugs found by @bcull
3. Added 20 comprehensive tests for missed paths
4. Documented failure in retrospective

**Long-term:**
1. User demanded 100% block coverage → new standard
2. Ban word "comprehensive" without metrics
3. Require coverage measurement before claims
4. Add user verification as QA gate

## Lessons Learned

### For Claims

**NEVER claim:**
- "comprehensive tests" without coverage metrics
- "sufficient coverage" without measuring
- "fully tested" without user scenario validation

**ALWAYS provide:**
- Coverage percentage: "X% block coverage"
- Path inventory: "Tests cover M of N branches"
- User verification: "User verified via [method]"

### For Testing

**Test invocation, not just implementation:**
- User runs via iex → Simulate iex
- User has env variables set → Test with variables
- User on Linux/macOS → Test cross-platform

**Measure before claiming:**
- Run Pester with `-CodeCoverage`
- Parse coverage percentage
- Fail if below threshold (90% min, 100% target)

### For Trust

**Trust is earned through evidence:**
- Green tests ≠ sufficient
- AI agents pass ≠ quality
- User verification = ground truth

**Trust is lost through false claims:**
- Claiming without measuring
- Overconfidence without verification
- Speed over accuracy

**Trust is rebuilt through honesty:**
- Admit when wrong
- Raise quality bar
- Document failures for learning

## Impact Assessment

### Stakeholders

**@bcull:**
- Had to perform multiple verification tests
- Found bugs that "comprehensive tests" missed
- Wasted time waiting for fixes
- Likely frustrated by quality gap

**User (rjmurillo):**
- Explicitly called out false claims
- Forced honest admission
- Raised quality bar to 100% block coverage
- Trust damaged but honest response preserved relationship

**Project:**
- PR merged with hidden defects
- Quality standard raised (100% coverage)
- Institutional learning documented

### Trust Score

**Before Incident:** Assumed high trust (AI agent, good intentions)
**After False Claim:** Low trust (claimed comprehensive, was inadequate)
**After Admission:** Rebuilding (honest, raised bar, documented)

**Trajectory:** Trust damage → honest admission → higher standards → recovery

## Prevention Protocol

### Before Claiming "Comprehensive"

1. Measure coverage: `Invoke-Pester -CodeCoverage`
2. Verify user scenario: Write test that mimics actual usage
3. Document paths: List conditionals, verify coverage
4. User verification: Get stakeholder to test

### Before Claiming "Ready"

1. Tests pass (necessary but insufficient)
2. Coverage meets threshold (90% min, 100% target)
3. User scenario validated
4. User verified (if applicable)

### Language Precision

**Replace vague claims with evidence:**
- "comprehensive tests" → "95% block coverage across 12 execution paths"
- "fully tested" → "User verified via iex on Windows, Linux, macOS"
- "ready to merge" → "Coverage 100%, user verified, all agents pass"

## Related Incidents

**Similar Pattern in PR #760:**
- AI agents pass, user finds bugs
- Static review misses execution gaps
- Pattern: Multiple validation layers create false confidence

**Root Cause Category:**
- Overconfidence from green tests
- No coverage measurement
- User verification not part of QA process

## Integration Points

**Testing Protocol:** Require coverage metrics before claiming sufficient
**QA Agent Review:** Add coverage parsing, flag vague claims
**Skillbook:** Tag as `usage-mandatory` for evidence-based claims
**HANDOFF.md:** Add quality standard: 100% block coverage target

## Skill Updates

**ADD:**
- Skill-Trust-Evidence-Based-Claims: Never claim without proof
- Skill-Language-Precision-Comprehensive: Ban "comprehensive" without metrics
- Skill-QA-User-Gate: Include user verification before merge-ready

**TAG:**
- This incident as evidence for coverage-first testing
- As case study for trust damage from false claims
- As forcing function for 100% coverage standard

## User Demand (Direct Quote from Summary)

> "I want 100% block coverage tests"

**Response:** Accepted. New standard for all PowerShell scripts.

## Retrospective Reference

Full analysis: `.agents/retrospective/2026-01-13-pr894-test-coverage-failure.md`

## Key Insight

**Claims without evidence = trust damage**
**Evidence-based claims = trust building**
**Green tests ≠ comprehensive testing**
**User verification = ground truth**
