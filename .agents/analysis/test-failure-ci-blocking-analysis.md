# Analysis: Test Failure CI Blocking Investigation

## 1. Objective and Scope

**Objective**: Investigate why test failures on main branch are not blocking PRs/merges in CI.

**Scope**:
- GitHub Actions workflows for Pester and pytest
- Path filtering configuration
- Test execution configuration
- Branch protection requirements
- Test suppression mechanisms

**Requested Context**: User reported "94 failing tests + 1 container failure" not caught by CI.

## 2. Context

The repository has comprehensive test infrastructure with Pester (PowerShell) and pytest (Python) tests. Tests run locally show only 3 Pester test failures on main branch, not 94. No container infrastructure exists.

Recent commits on main (as of 2026-02-07):
- d291f2c9: docs changes only
- c6288f7a: fix changes
- 0000ccc6: fix changes
- 16e6b3b1: docs changes
- 791350d0: fix changes

All recent workflow runs show success status despite local test failures.

## 3. Approach

**Methodology**:
1. Read GitHub Actions workflow files
2. Analyze path filtering configuration
3. Run tests locally on main branch
4. Check recent workflow runs via GitHub API
5. Examine test runner scripts for suppression

**Tools Used**:
- Read (workflow files, test scripts)
- Bash (git commands, gh CLI, local test runs)
- Grep (search for suppression patterns)

**Limitations**:
- Cannot access branch protection settings (404 error from API)
- User's "94 failing tests" claim could not be reproduced (only 3 failures found)
- No container infrastructure found in repository

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Tests skipped on recent main commits | `gh run view 21787113978` | High |
| Path filtering excludes docs-only changes | `.github/workflows/pester-tests.yml:66-75` | High |
| Only 3 Pester test failures on main | Local test run | High |
| No test suppression (continue-on-error, etc.) | Workflow file analysis | High |
| Workflow reports success when tests skipped | GitHub Actions job conclusions | High |
| 860 Python tests passing | Local pytest run | High |

### Facts (Verified)

**Workflow Configuration** (`.github/workflows/pester-tests.yml`):
- Lines 26-35: Runs on push to main, feat/**, fix/** branches and PRs to main
- Lines 38-83: `check-paths` job uses `dorny/paths-filter` to determine if tests should run
- Line 46: `should-run-tests` output is `true` only if testable files changed OR workflow_dispatch
- Lines 66-75: Testable paths filter includes:
  - `scripts/**`
  - `build/**`
  - `.github/scripts/**`
  - `.github/tests/**`
  - `.github/workflows/pester-tests.yml`
  - `.claude/skills/**`
  - `tests/**`
  - `.baseline/**`
- Lines 85-130: `test` job runs ONLY if `should-run-tests == 'true'`
- Line 102: Test script invoked with `-CI -EnableCodeCoverage -CheckCoverageThreshold`
- Line 129: `fail-on-error: true` configured for test reporter
- Lines 202-238: `skip-tests` job runs when `should-run-tests != 'true'`
- Line 238: Skip job uses `fail-on-error: false` for test reporter

**Test Runner Configuration** (`build/scripts/Invoke-PesterTests.ps1`):
- Line 231: `$config.Run.Exit = $CI.IsPresent` - exits with error code in CI mode
- Lines 389-402: Displays failed tests but ONLY exits 1 if failures exist
- Lines 526-528: Local runs exit with code 1 on failures
- No suppression mechanisms (no `|| true`, no `continue-on-error`)

**Recent Workflow Runs**:
- Run ID 21787113978 (most recent): SUCCESS
  - Job "Check Changed Paths": success
  - Job "Skip PSScriptAnalyzer (No Changes)": success
  - Job "Skip Pester Tests (No Changes)": success
  - Job "Run Pester Tests": SKIPPED
  - Job "Run PSScriptAnalyzer": SKIPPED

**Local Test Results**:
- Main branch: 912 tests run, 895 passed, 3 failed, 14 skipped
- Failed tests (ThreadId format validation):
  1. `Get-ThreadById.ps1` - PRRT_ prefix validation
  2. `Unresolve-PRReviewThread.ps1` - PRRT_ prefix validation
  3. `Get-ThreadConversationHistory.ps1` - PRRT_ prefix validation
- Python tests: 860 passed, 1 skipped

### Hypotheses (Unverified)

1. User's "94 failing tests" refers to a different branch or PR
2. User ran tests with different parameters/configuration
3. Branch protection is not configured to require "Pester Tests" status check

## 5. Results

### Primary Issue Identified

**Path filtering causes tests to be skipped on docs-only commits, but the "skip" job reports success.**

Recent commits on main changed only documentation files:
- `.agents/AGENT-SYSTEM.md`
- `.agents/SESSION-PROTOCOL.md`
- `.agents/governance/TESTING-ANTI-PATTERNS.md`
- `.agents/sessions/*.json`
- `.serena/memories/*.md`

None of these paths match the testable filter in lines 66-75, so:
1. `check-paths` job sets `should-run-tests: false`
2. `test` job is skipped (never runs)
3. `skip-tests` job runs instead and reports SUCCESS
4. Overall workflow status: SUCCESS

**The 3 actual test failures on main are never detected because tests never run.**

### Secondary Issue

Test failures exist on main branch (3 Pester tests failing), but:
- Path filtering prevents test execution on docs-only commits
- When tests DO run (on code changes), they WILL fail and block (configuration is correct)
- Tests have been failing silently because recent commits were documentation-only

### Configuration Assessment

| Configuration Item | Status | Notes |
|-------------------|--------|-------|
| Test runner fails on error | [PASS] | Lines 231, 389-402, 526-528 exit with code 1 |
| Workflow fails on test error | [PASS] | Line 129 `fail-on-error: true` |
| Path filtering configured | [PASS] | Lines 66-75 define testable paths |
| Skip job reports failure | [FAIL] | Line 238 `fail-on-error: false` |
| Branch protection enabled | [UNKNOWN] | API returned 404 |

## 6. Discussion

### Root Cause

Recent commits on main branch changed only documentation files not covered by the testable path filter. The path filtering design intentionally skips test execution when no code changes, which is cost-efficient. However, this creates a scenario where:

1. Tests fail on a feature branch
2. Feature branch is merged to main
3. Next commit on main is docs-only
4. Tests are skipped, workflow shows success
5. Broken tests on main are not visible in CI

### Path Filter Design Tradeoff

The testable path filter EXCLUDES:
- `.agents/**` (except planning artifacts referenced by code)
- `.serena/**`
- Documentation files outside code directories
- Session logs

This is intentional for cost optimization (ADR-025 mentions ARM runner savings). However, it creates a blind spot: **tests are never re-run on main after docs-only commits, even if previous commits broke them.**

### Why 3 Tests Are Failing

The 3 failing tests (ThreadId format validation) appear to be legitimate test failures introduced in recent code changes. They would have been caught if those changes had been pushed directly, but if they came through a PR that was merged, subsequent docs-only commits on main never re-validated.

### User's "94 Failing Tests" Discrepancy

Local execution shows:
- Pester: 3 failures (not 94)
- pytest: 0 failures (860 passed)
- Total: 3 failures

The "94 failing tests + 1 container failure" claim cannot be reproduced. Possible explanations:
1. User ran tests on different branch
2. User ran tests with different configuration
3. User misread test output (912 total tests vs 3 failures)
4. Test state changed between user's report and this analysis

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Fix 3 failing tests immediately | Broken tests on main undermine CI confidence | 1 hour |
| P0 | Add periodic full test run on main | Catch issues missed by path filtering | 2 hours |
| P1 | Require test status check in branch protection | Prevent merges with failing tests | 30 minutes |
| P1 | Make skip job fail if tests previously failed | Surface hidden failures after docs commits | 2 hours |
| P2 | Add `.agents/**` to testable paths if tests exist | Ensure test coverage for agent code | 1 hour |

### Detailed Recommendations

#### 1. Fix Failing Tests (P0)

**Files to fix**:
- `.claude/skills/github/scripts/pr/Get-ThreadById.ps1:63`
- `.claude/skills/github/scripts/pr/Unresolve-PRReviewThread.ps1:157`
- `.claude/skills/github/scripts/pr/Get-ThreadConversationHistory.ps1:68`

**Issue**: ThreadId format validation expects `PRRT_` prefix but tests are passing different format.

**Action**: Review ThreadId format requirements and either:
- Fix the validation logic to accept correct format, OR
- Fix the test data to provide correct format

#### 2. Add Periodic Full Test Run (P0)

**Create new workflow**: `.github/workflows/scheduled-tests.yml`

```yaml
name: Scheduled Full Test Run

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:

jobs:
  test:
    name: Run All Tests
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Pester Tests
        shell: pwsh
        run: ./build/scripts/Invoke-PesterTests.ps1 -CI -EnableCodeCoverage -CheckCoverageThreshold
```

**Rationale**: Ensures tests run regularly even if only docs change, catching issues missed by path filtering.

#### 3. Require Test Status Check (P1)

**Action**: Configure branch protection via GitHub UI or API:

```bash
gh api repos/:owner/:repo/branches/main/protection \
  -X PUT \
  -f required_status_checks[strict]=true \
  -f required_status_checks[contexts][]=Pester Tests \
  -f required_status_checks[contexts][]=Python Tests
```

**Rationale**: Prevents PRs with failing tests from merging.

#### 4. Track Test Failures Across Commits (P1)

**Modify workflow**: Add job to check if tests failed in recent main commits.

**Implementation approach**:
1. Store test results as artifact on every main commit
2. Before running skip job, check if last real test run failed
3. If last run failed and current is skip, report FAIL instead of success

**Complexity**: Requires workflow state management across runs.

**Alternative (simpler)**: Remove skip jobs entirely, always run tests (higher cost but simpler).

#### 5. Expand Testable Paths (P2)

**Current exclusion**: `.agents/**` directory is excluded from testable paths.

**Question to answer**: Are there PowerShell modules or scripts in `.agents/` that have tests?

**If yes**: Add to testable paths filter.

**If no**: Document why `.agents/` is excluded (documentation only).

## 8. Conclusion

**Verdict**: Configuration is mostly correct, but path filtering creates blind spot.

**Confidence**: High

**Rationale**: Path filtering intentionally skips tests on docs-only commits for cost optimization. This design is sound but creates a scenario where broken tests on main are not visible after docs commits. The 3 actual test failures need immediate fixing.

### User Impact

**What changes for you**:
1. CI will catch test failures on main branch after docs-only commits
2. PRs with failing tests will be blocked from merging
3. Visibility into test health improves

**Effort required**:
- Fix 3 tests: 1 hour
- Add scheduled workflow: 30 minutes
- Configure branch protection: 30 minutes
- Total: 2 hours

**Risk if ignored**:
- Broken tests accumulate on main
- CI loses credibility as quality gate
- Developers lose confidence in test suite
- Production bugs increase

## 9. Appendices

### Sources Consulted

- `.github/workflows/pester-tests.yml` (Pester test workflow)
- `.github/workflows/pytest.yml` (Python test workflow)
- `.github/workflows/pr-validation.yml` (PR validation workflow)
- `build/scripts/Invoke-PesterTests.ps1` (Test runner script)
- GitHub Actions runs via `gh run list` and `gh run view`
- Local test execution on main branch
- Git commit history and file changes

### Data Transparency

**Found**:
- Workflow configurations and path filters
- Test runner implementation
- Recent workflow run status and job details
- Local test results (3 failures)
- File changes in recent commits

**Not Found**:
- Branch protection configuration (API 404)
- Evidence of "94 failing tests" claim
- Container infrastructure or tests
- Test suppression mechanisms (none exist)

### Files Requiring Changes

If implementing recommendations:

1. **Fix tests** (P0):
   - `.claude/skills/github/scripts/pr/Get-ThreadById.ps1`
   - `.claude/skills/github/scripts/pr/Unresolve-PRReviewThread.ps1`
   - `.claude/skills/github/scripts/pr/Get-ThreadConversationHistory.ps1`
   - OR their corresponding test files if test data is wrong

2. **Add scheduled tests** (P0):
   - `.github/workflows/scheduled-tests.yml` (new file)

3. **Branch protection** (P1):
   - GitHub UI or API call (no file changes)

4. **Track failures across commits** (P1):
   - `.github/workflows/pester-tests.yml` (modify skip jobs)
   - Requires artifact storage strategy

5. **Expand testable paths** (P2):
   - `.github/workflows/pester-tests.yml:66-75` (add paths if needed)
