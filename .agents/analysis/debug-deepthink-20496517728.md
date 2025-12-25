# Analysis: PR Maintenance Workflow "Ran But Didn't Do Anything"

**Issue**: [#394](https://github.com/rjmurillo/ai-agents/issues/394)
**Workflow Run**: [20496517728](https://github.com/rjmurillo/ai-agents/actions/runs/20496517728/job/58896964543)
**Date**: 2025-12-25

## Problem Statement

Workflow run 20496517728 executed successfully (exit code 0) but processed 0 PRs without clear explanation why.

## Root Cause Analysis

The PR Maintenance script (`scripts/Invoke-PRMaintenance.ps1`) has two early exit conditions that return success but process no PRs:

### Exit Condition 1: Lock Held (Lines 909-922)
```powershell
if (-not (Enter-ScriptLock)) {
    Write-Log "Exiting: another instance is running" -Level WARN
    exit 0
}
```

**Trigger**: Another PR maintenance instance is already running
**Behavior**: Exit with code 0, log warning, process 0 PRs
**Visibility**: Console log only (no GitHub Actions step summary)

### Exit Condition 2: Rate Limit Low (Lines 927-961)
```powershell
if (-not (Test-RateLimitSafe)) {
    Write-Log "Exiting: API rate limit too low" -Level WARN
    exit 0
}
```

**Trigger**: GitHub API rate limit below thresholds (core < 100, search < 15, etc.)
**Behavior**: Exit with code 0, log warning, process 0 PRs
**Visibility**: Console log only (no GitHub Actions step summary)

## Why This Was Confusing

Both exit conditions:
1. Return success (exit code 0) - workflow shows as ✅ passed
2. Log only to console - easy to miss in large log files
3. Don't write to `$env:GITHUB_STEP_SUMMARY` - no visible summary in GitHub UI
4. Result: Appears workflow "ran but didn't do anything"

## Solution Implemented

Added GitHub Actions step summary output for both early exit conditions:

### Lock Held Summary
```markdown
## PR Maintenance - Early Exit

**Status**: Skipped (another instance running)
**PRs Processed**: 0
**Reason**: Concurrent execution detected - another PR maintenance instance is already running.

This is expected behavior when multiple workflow runs overlap. The concurrent run will handle PR processing.
```

### Rate Limit Summary
```markdown
## PR Maintenance - Early Exit

**Status**: Skipped (rate limit too low)
**PRs Processed**: 0
**Rate Limit**: 50 / 5000 remaining
**Resets In**: 30 minutes (at 2025-12-25 02:00:00 UTC)

The workflow will automatically retry on the next hourly schedule once the rate limit resets.
```

## Verification

The original workflow run (20496517728) likely hit one of these conditions:
- Most probable: Rate limit threshold (API calls exhausted by other workflows)
- Less probable: Lock held (concurrent execution)

Without access to the actual logs, definitive determination requires either:
1. Checking the uploaded workflow artifacts (`pr-maintenance-logs`)
2. Re-running the workflow with the fix applied

## Impact

Future workflow runs will now:
- Clearly indicate why 0 PRs were processed
- Show rate limit status and reset time
- Provide actionable information for troubleshooting

## Files Modified

- `scripts/Invoke-PRMaintenance.ps1`: Added step summary output for early exits

## Testing

Verified summary output generates correctly for both scenarios using mock conditions.

## Next Steps

Monitor next hourly PR maintenance run to verify:
1. Summary output appears correctly
2. No regression in normal processing flow
3. Early exit conditions are clearly communicated
