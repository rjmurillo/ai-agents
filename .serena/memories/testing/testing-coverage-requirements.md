# Testing Coverage Requirements

## Context

**Source**: PR #894 retrospective (2026-01-13)
**Incident**: Claimed "comprehensive tests" (63 pass) with 0% remote execution path coverage; user found 2 bugs
**User Demand**: 100% block coverage for all PowerShell scripts

## Coverage-First Testing Protocol

### BLOCKING Requirements

1. **Measure Before Claiming**
   - Run Pester with `-CodeCoverage` parameter
   - Verify block coverage percentage
   - Target: 100% block coverage (minimum 90%)
   - NEVER use words "comprehensive" or "sufficient" without metrics

2. **Test User Scenario First**
   - Write at least one test that mimics actual user invocation
   - Example: For iex scripts, simulate by clearing `$PSScriptRoot`
   - Validate in production-like context, not just implementation correctness

3. **Execution Path Inventory**
   - Identify all conditional branches (`if`, `switch`, `try-catch`)
   - Document which tests cover which paths
   - Require tests for EACH branch
   - Example: `if ($IsRemoteExecution)` requires tests for TRUE and FALSE paths

4. **User Verification QA Gate**
   - Include user verification BEFORE claiming merge-ready
   - Not accidental, deliberate step in QA process
   - Ask: "Did the actual user verify this fix?"

### Language Rules

**BANNED without metrics:**
- "comprehensive tests"
- "sufficient coverage"
- "fully tested"

**REQUIRED format:**
- "X% block coverage across N execution paths"
- "Tests cover M of N conditional branches"
- "User verified via [method]"

### Pester Integration

```powershell
# Run tests with coverage measurement
Invoke-Pester -Path ./scripts/tests/*.Tests.ps1 `
    -CodeCoverage ./scripts/*.ps1 `
    -CodeCoverageOutputFile coverage.xml

# Parse coverage output
$Coverage = (Select-Xml -Path coverage.xml -XPath "//coverage/@line-rate").Node.Value
$CoveragePercent = [math]::Round([double]$Coverage * 100, 2)

# Fail if below threshold
if ($CoveragePercent -lt 90) {
    Write-Error "Coverage $CoveragePercent% below 90% threshold"
    exit 1
}
```

## Evidence

**PR #894 Failures:**
- Tested parameter validation (what changed) ✅
- Tested remote execution path (what runs) ❌
- Result: User found 2 bugs in first verification

**Execution Path Gap:**
- Line 227: `if ($IsRemoteExecution)` creates TWO paths
- Tests ran locally: `$PSScriptRoot` set → `$IsRemoteExecution = $false`
- User ran via iex: `$PSScriptRoot` not set → `$IsRemoteExecution = $true`
- Bugs at lines 250, 198: Both in TRUE branch, never tested

**Coverage Math:**
- Local path: 100% coverage (tested)
- Remote path: 0% coverage (not tested)
- Overall: ~50% actual coverage
- Claimed: "comprehensive" (false)

## Trust Impact

**User Response:** "you claim you have tests...either (1) tests not run, (2) grossly inadequate coverage, or (3) you're lying"

**Admission:** "Option 2: inadequate coverage"

**Consequence:** User demanded 100% block coverage as new standard

## Integration Points

**Testing Protocol:** Add coverage measurement step before test sign-off
**QA Agent Review:** Parse coverage.xml output, require metrics in PR description
**AI Quality Gates:** Cannot detect coverage gaps via static analysis alone
**Skill System:** Tag as [usage-mandatory](usage-mandatory.md) for all PowerShell testing

## Related Patterns

- `.serena/memories/skills-powershell-patterns.md` - Glob-to-regex conversion order
- `.agents/retrospective/2026-01-13-pr894-test-coverage-failure.md` - Full retrospective
- Issue #892, PR #894 - Source incident
