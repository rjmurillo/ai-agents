# ADR-022: Enhanced Logging and GITHUB_OUTPUT

## Status

Accepted

## Date

2025-12-25

## Context

### Problem

Workflow run 20496517728 executed successfully but processed 0 PRs with no clear indication why. The script had minimal logging at decision points, making troubleshooting difficult:

- Early exits (rate limit) logged one line to console
- No visibility into script execution flow
- No structured outputs for workflow consumption
- GitHub Actions step summary not populated

When investigating "why didn't anything happen," operators had to:
1. Download workflow logs
2. Search through large log files
3. Infer state from sparse log messages

### Forces

- **Observability**: Need stream-of-thought logging for debugging unexpected states
- **Workflow Integration**: GitHub Actions steps need structured data via `GITHUB_OUTPUT`
- **User Experience**: Step summary should explain what happened in UI
- **Performance**: Logging adds overhead (minimal for this workload)
- **Maintenance**: Verbose logging can obscure important messages

## Decision

**Implement comprehensive logging throughout PR Maintenance script with three tiers:**

1. **Console Logging** (existing `Write-Log`):
   - Add detailed logging at all decision points
   - Log inputs, outputs, and state transitions
   - Include environment/system info at startup

2. **GITHUB_OUTPUT** (structured data):
   - Write key metrics and exit reasons
   - Enable workflow steps to consume results
   - Format: `key=value` lines

3. **GITHUB_STEP_SUMMARY** (UI visibility):
   - Write markdown summaries for early exits
   - Show rate limits, wait times, next actions
   - Make "nothing happened" cases explicit

## Rationale

### Stream of Thought Logging

When debugging unexpected behavior, logs should answer:
- "How did the program get to this state?"
- "What did it do after?"
- "What was it thinking?"

This requires logging:
- Before decisions: "Checking rate limits..."
- At decisions: "Rate limit check: 50/5000 remaining - OK"
- After decisions: "Proceeding with PR processing"

### GITHUB_OUTPUT Integration

GitHub Actions workflow steps can consume outputs:
```yaml
- name: Run maintenance
  id: maintenance
  run: ./scripts/Invoke-PRMaintenance.ps1

- name: Create alert
  if: steps.maintenance.outputs.blocked_count > 0
  run: ...
```

This enables:
- Conditional workflow steps
- Metrics collection
- Downstream automation

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Minimal logging | Low overhead, clean logs | Hard to debug | Poor observability |
| Debug flag only | Clean default, detailed on demand | Must anticipate debug needs | Can't debug past runs |
| Structured logging (JSON) | Machine-parseable | Harder to read for humans | Overkill for this use case |
| **Verbose + outputs** | Easy debugging, workflow integration | Larger logs | **Chosen** - best balance |

### Trade-offs

**Gains:**
- Faster incident response (logs show execution flow)
- Better workflow automation (structured outputs)
- Clearer UI (step summaries)
- Easier onboarding (logs teach how script works)

**Costs:**
- Larger log files (~2x size estimate)
- Slightly longer execution time (< 1%)
- More lines of code to maintain

**Future Option:**
Use `$env:RUNNER_DEBUG` to toggle verbosity:
```powershell
$verbose = $env:RUNNER_DEBUG -eq '1'
if ($verbose) { Write-Log "Detailed message..." }
```

## Consequences

### Positive

- **Troubleshooting**: "Ran but didn't do anything" cases immediately clear from logs
- **Automation**: Workflow can react to script outputs (blocked PRs, errors)
- **Transparency**: Step summary shows users what happened without checking logs
- **Documentation**: Logs serve as execution trace for understanding script behavior

### Negative

- **Log Volume**: Logs may be 2-3x larger (mitigation: future DEBUG flag)
- **Maintenance**: More log statements to keep in sync with code changes

### Neutral

- **Standards**: Establishes logging pattern for other automation scripts
- **Baseline**: Current verbose level becomes the standard

## Implementation Notes

### Console Logging Pattern

**At script start:**
```powershell
Write-Log "=== PR Maintenance Starting ===" -Level INFO
Write-Log "Script: $PSCommandPath" -Level INFO
Write-Log "PowerShell: $($PSVersionTable.PSVersion)" -Level INFO
Write-Log "Repository: $Owner/$Repo" -Level INFO
```

**At decision points:**
```powershell
Write-Log "Checking API rate limits..." -Level INFO
if (-not (Test-RateLimitSafe)) {
    Write-Log "EARLY EXIT: API rate limit too low" -Level WARN
    # ... handle exit
}
Write-Log "API rate limits OK - proceeding" -Level INFO
```

**At state transitions:**
```powershell
Write-Log "Starting PR maintenance processing (MaxPRs: $MaxPRs)..." -Level INFO
$results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -MaxPRs $MaxPRs
Write-Log "PR maintenance processing complete" -Level INFO
```

### GITHUB_OUTPUT Format

```powershell
if ($env:GITHUB_OUTPUT) {
    "exit_reason=rate_limit_low" | Out-File $env:GITHUB_OUTPUT -Append
    "prs_processed=0" | Out-File $env:GITHUB_OUTPUT -Append
    "comments_acknowledged=5" | Out-File $env:GITHUB_OUTPUT -Append
    "conflicts_resolved=2" | Out-File $env:GITHUB_OUTPUT -Append
    "blocked_count=1" | Out-File $env:GITHUB_OUTPUT -Append
    "error_count=0" | Out-File $env:GITHUB_OUTPUT -Append
}
```

### GITHUB_STEP_SUMMARY Format

Use markdown for readability:
```markdown
## PR Maintenance - Early Exit

**Status**: Skipped (rate limit too low)
**PRs Processed**: 0
**Rate Limit**: 50 / 5000 remaining
**Resets In**: 30 minutes (at 2025-12-25 02:00:00 UTC)

The workflow will automatically retry on the next hourly schedule once the rate limit resets.
```

### Error Logging

Always log:
- Exception type
- Exception message
- Stack trace

```powershell
catch {
    Write-Log "FATAL ERROR: $_" -Level ERROR
    Write-Log "Exception Type: $($_.Exception.GetType().FullName)" -Level ERROR
    Write-Log "Stack Trace: $($_.ScriptStackTrace)" -Level ERROR
}
```

## Related Decisions

- **ADR-021**: Remove No-Op Lock Functions - Removing lock logging makes enhanced logging more important
- **ADR-015**: PR Automation Concurrency and Safety - Established the workflow patterns we're enhancing observability for

## References

- GitHub Actions Outputs: https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#setting-an-output-parameter
- GitHub Actions Step Summary: https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#adding-a-job-summary
- Issue #394: Original "ran but didn't do anything" report
