# AI PR Quality Gate - Infrastructure Handling Update (2025-12-27)

## Summary

- Updated `.github/actions/ai-review/action.yml` so infrastructure failures (timeouts/rate limits, no stdout/stderr) that exhaust retries no longer exit the job.
- When infrastructure retries are exhausted, the action emits a fallback output with `VERDICT: CRITICAL_FAIL`, a clear infrastructure message, and preserves `infrastructure_failure=true`, allowing the job to continue so artifacts are produced.
- Added attempt counting before breaking out of the retry loop to keep `retry_count` non-negative and accurate.
- Non-infrastructure errors still fail fast; only infrastructure failures that exhaust retries are downgraded by aggregation to WARN instead of blocking the workflow.

## Rationale

- Prevent PRs from failing due to transient Copilot CLI issues while keeping visibility via the infrastructure-failure label and WARN verdict.

## Tests

- `pwsh build/scripts/Invoke-PesterTests.ps1 -CI` (baseline and post-change) passed.

## Session 96 Updates (2025-12-28)

- Simplified retry count tracking: added dedicated `RETRY_COUNT` variable instead of computing from `ATTEMPT`
- Removed dead timeout check block (exit code 124 already handled by `is_infrastructure_failure()`)
- Restored `Test-PRMerged.ps1` and tests that were accidentally deleted during merge conflict resolution

## Impact

- Aggregation job now runs even when Copilot CLI retries exhaust, enabling WARN verdict with infra label instead of workflow failure.
- Retry count output reflects actual attempts, aiding observability.
