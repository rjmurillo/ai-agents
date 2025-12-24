# Skill-CI-001: Copilot CLI Authentication Failures

## Statement

When Copilot CLI returns exit code 1 with no stdout/stderr output, this indicates an authentication or access issue with the bot account, not a code review failure.

## Atomicity Score: 92%

## Impact: 7/10

## Context

The AI PR Quality Gate workflow uses `gh copilot` CLI for AI-powered code reviews. When the bot account lacks proper Copilot access, the CLI silently fails.

## Pattern

### Symptoms

```text
Exit code: 1
Stdout length: 0 chars
Stderr length: 0 chars
```

### Root Cause Analysis

1. **Authentication Issues**
   - Bot token doesn't have Copilot CLI access
   - `GITHUB_TOKEN` in workflow lacks required permissions
   - Copilot not enabled for the repository/organization

2. **Rate Limiting**
   - Too many Copilot API requests in short time
   - Multiple parallel agents exhausting quota

3. **Network Issues**
   - Unable to reach Copilot API endpoints
   - Transient connectivity failures

### Workflow Impact

When DevOps agent returns `CRITICAL_FAIL` due to Copilot CLI failure:

- `Aggregate Results` step fails the entire PR
- All AI reviews may appear to fail even though code is fine
- Multiple PRs blocked simultaneously

## Mitigation

1. **Verify bot account Copilot access**

   ```bash
   gh copilot --help  # Should work if access enabled
   ```

2. **Check workflow permissions**
   - Ensure `contents: read` and `pull-requests: write` permissions
   - Bot account needs Copilot CLI access in organization settings

3. **Consider graceful degradation**
   - Treat Copilot CLI failures as WARN, not CRITICAL_FAIL
   - Allow human override for authentication issues

## Evidence

Session 04 (2025-12-24): Identified that bot account lacks Copilot access. DevOps agent returned `CRITICAL_FAIL` with no output, blocking all PRs.

**Fix Applied**: Changed `.github/actions/ai-review/action.yml` to emit `WARN` instead of `CRITICAL_FAIL` when authentication fails (no stdout AND no stderr). This allows PRs to proceed while still flagging infrastructure issues.

## Resolution

For auth failures (no output), the composite action now:

1. Emits GitHub Actions `::warning::` annotation
2. Returns `VERDICT: WARN` instead of `CRITICAL_FAIL`
3. Includes message explaining this is infrastructure, not code quality
