# Issue #338: Copilot CLI Retry Logic Implementation

**Date**: 2025-12-24
**Status**: Implemented (not yet pushed)
**Branch**: `fix/issue-357-rca-documentation`
**Commit**: `888cc39`

## Summary

Implemented retry logic with exponential backoff and fail-fast behavior for Copilot CLI failures in `.github/actions/ai-review/action.yml`.

## Changes Made

### 1. Retry Timing (per #338 spec)

```bash
RETRY_DELAYS=(0 10 30)  # seconds before each attempt
```

| Attempt | Wait Before | Total Elapsed |
|---------|-------------|---------------|
| 1 | 0s | 0s |
| 2 | 10s | 10s |
| 3 | 30s | 40s |

### 2. Fail-Fast Behavior

Instead of returning `CRITICAL_FAIL` verdict (which gets obscured in aggregation), the job now exits with code 1 for infrastructure failures:

- All retries exhausted with no output → `exit 1`
- Timeout occurs → `exit 1`
- CLI produces stderr but no stdout → `exit 1`

### 3. Clear Error Messages

```
::error::=== INFRASTRUCTURE FAILURE - JOB FAILED ===
::error::Copilot CLI failed after 3 attempts with no output.
::error::
::error::LIKELY CAUSE: COPILOT_GITHUB_TOKEN secret is expired or misconfigured.
::error::
::error::TO FIX:
::error::  1. Check Repository Settings > Secrets > COPILOT_GITHUB_TOKEN
::error::  2. Ensure the token has 'copilot' scope
::error::  3. Verify the GitHub account has Copilot access enabled
```

## Why This Matters

Before: Infrastructure failures returned `CRITICAL_FAIL` verdict, got aggregated with other agent results, made it hard to identify root cause.

After: Job fails immediately with clear error message visible in GitHub Actions UI. No need to dig through aggregate results.

## Related

- Issue #338: Add retry logic with backoff for Copilot CLI failures
- Issue #357: AI PR Quality Gate aggregation failures (RCA)
- Issue #328: Handle infrastructure failures (original categorization)

## Files Modified

- `.github/actions/ai-review/action.yml` (+53/-36 lines)

## Testing

Not locally testable (requires CI environment with Copilot access). Will be validated when PR is merged and workflows run.
