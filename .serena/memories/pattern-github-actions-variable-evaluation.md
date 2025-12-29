# Pattern: GitHub Actions Variable Evaluation

## Problem

GitHub Actions expressions (`${{ }}`) are evaluated at YAML parse time, not at runtime. This causes failures when expressions reference variables that don't exist for certain event types.

## Example

**Failing Code** (issue #348):
```yaml
if ($env:GITHUB_EVENT_NAME -eq 'pull_request') {
  $diffOutput = git diff --name-only origin/${{ github.base_ref }}...HEAD
```

**Why It Failed**:
1. `${{ github.base_ref }}` evaluated at YAML parse time (before workflow runs)
2. For `push` events, `github.base_ref` is empty
3. YAML parser substitutes empty string: `origin/...HEAD` (invalid git syntax)
4. Git returns exit code 129 (usage error)

## Solution

Use environment variables instead of GitHub Actions expressions inside PowerShell scripts:

**Fixed Code**:
```yaml
if ($env:GITHUB_EVENT_NAME -eq 'pull_request') {
  $diffOutput = git diff --name-only origin/$env:GITHUB_BASE_REF...HEAD
```

**Why It Works**:
- `$env:GITHUB_BASE_REF` evaluated at PowerShell runtime
- Conditional ensures code only runs when variable is populated
- Other event types skip this branch entirely

## Rule

| Use This | When | Example |
|----------|------|---------|
| `${{ }}` expressions | Static values, workflow control | `runs-on: ${{ matrix.os }}` |
| `$env:VAR` | Inside PowerShell scripts | `$env:GITHUB_BASE_REF` |
| `${VAR}` | Inside bash scripts | `${GITHUB_BASE_REF}` |

## Variable Availability

From [GitHub Actions Documentation](https://docs.github.com/en/actions/learn-github-actions/variables#default-environment-variables):

| Variable | Available For | Description |
|----------|---------------|-------------|
| `GITHUB_BASE_REF` | `pull_request`, `pull_request_target` | PR target branch |
| `GITHUB_HEAD_REF` | `pull_request`, `pull_request_target` | PR source branch |
| `GITHUB_SHA` | All events | Commit SHA |
| `GITHUB_EVENT_NAME` | All events | Event type |

**Key Insight**: Variables with limited availability must be guarded by conditionals when used in scripts.

## Testing Strategy

1. **Verify conditional flow**: Trace execution for each event type
2. **Check variable availability**: Confirm variable exists before use
3. **Test on actual events**: CI runs provide real validation

## References

- Issue: #348
- Commit: b7d67f40404a276c74dfa4ed6d40e00d92ef6db1
- File: `.github/workflows/memory-validation.yml`
- Test Report: `.agents/qa/001-issue-348-test-report.md`
