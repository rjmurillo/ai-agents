# Incident Report: PR Maintenance Workflow False-Positive Failure Alert

## Incident Summary

**Date**: 2025-12-24 00:25:47 UTC
**Duration**: ~7 hours (until fix deployed)
**Severity**: P2 (Medium) - False-positive failure alerts, actual automation working correctly
**Impact**: Misleading alert created for successful workflow run with blocked PRs

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2025-12-24 00:25:29 | PR maintenance workflow started successfully |
| 2025-12-24 00:25:45 | Script completed successfully: 12 PRs processed, 25 comments acknowledged, 6 blocked PRs identified |
| 2025-12-24 00:25:45 | Script exited with code 1 (blocked PRs present) |
| 2025-12-24 00:25:47 | Workflow marked as failed due to exit code 1 |
| 2025-12-24 00:25:47 | Alert issue created by "Notify on failure" step |
| 2025-12-24 07:00:00 | Investigation revealed false-positive failure |
| 2025-12-24 07:15:00 | Fix implemented: script now exits 0 when blocked PRs exist |
| 2025-12-24 07:30:00 | Documentation updated with correct exit code semantics |

## Root Cause

**Primary cause**: The PR maintenance script exits with code 1 when blocked PRs are found (PRs with CHANGES_REQUESTED status). This exit code triggers the workflow's `failure()` condition, causing the "Notify on failure" step to create an alert issue.

**Design issue**: Exit code 1 was used to indicate "partial success" (blocked PRs exist), but GitHub Actions treats any non-zero exit code as a failure. The workflow has a dedicated step to handle blocked PRs (line 95-105), so the script should exit 0 for successful runs even when blocked PRs are reported.

**Why it's not a real failure**: 
- Script executed successfully ✅
- 12 PRs processed ✅  
- 25 comments acknowledged ✅
- 6 blocked PRs correctly identified ✅
- Logs properly saved ✅

The blocked PRs requiring CHANGES_REQUESTED are **expected workflow states**, not errors.

**Contributing factors**:
1. Exit code semantics misaligned with GitHub Actions expectations
2. Workflow failure condition (`if: failure()`) triggers on any non-zero exit
3. No distinction between "informational exit" (blocked PRs) and "error exit" (script failure)

## Impact Analysis

### Actual Workflow Performance

The workflow **executed successfully**:

| Metric | Value | Status |
|--------|-------|--------|
| PRs processed | 12 | ✅ Success |
| Comments acknowledged | 25 | ✅ Success |
| Conflicts resolved | 0 | ✅ N/A |
| Blocked PRs identified | 6 | ℹ️ Informational |
| Execution time | 16 seconds | ✅ Normal |
| API rate limits | All OK | ✅ Healthy |

### Blocked PRs (Expected State)

The following PRs had `CHANGES_REQUESTED` review status (expected, not errors):

1. PR #302 - docs(adr): ADR-017 PowerShell output schema consistency
2. PR #285 - perf: Add -NoProfile to pwsh invocations
3. PR #269 - docs(orchestrator): Phase 4 pre-PR validation
4. PR #255 - feat(github-skill): enhance skill for Claude
5. PR #247 - feat: technical guardrails for autonomous agents
6. PR #235 - feat(github-skills): add issue comments support

### False-Positive Impact

| Area | Impact | Severity |
|------|--------|----------|
| Alert noise | 1 unnecessary alert issue created | Medium |
| On-call burden | Dev investigated non-issue | Low |
| Monitoring accuracy | False failure rate increased | Medium |
| Team confidence | Workflow reliability perception reduced | Low |

## Resolution

### Immediate fix (2025-12-24 07:15 UTC)

Modified `Invoke-PRMaintenance.ps1` exit code logic:

```powershell
# Before (caused false-positive failures)
$exitCode = 0
if ($results.Errors.Count -gt 0) {
    $exitCode = 2
}
elseif ($results.Blocked.Count -gt 0) {
    $exitCode = 1  # ← This triggered workflow failure
}

# After (correct semantics)
$exitCode = 0
if ($results.Errors.Count -gt 0) {
    $exitCode = 2
}
# Blocked PRs no longer cause non-zero exit
# They're handled by dedicated workflow step (line 95-105)
```

### Exit Code Semantics Clarified

| Exit Code | Meaning | Workflow Behavior |
|-----------|---------|-------------------|
| 0 | Success (PRs processed, blocked PRs reported) | ✅ Passes |
| 1 | Reserved for future use | N/A |
| 2 | Fatal errors (script failure, API errors) | ❌ Fails |

### Files Modified

- `scripts/Invoke-PRMaintenance.ps1`: Exit code logic and documentation
- `.agents/devops/incident-2025-12-24-pr-maintenance-exit-code.md`: Incident report (this file)

## Prevention Measures

### Implemented

1. ✅ **Corrected exit code semantics** - Script exits 0 for successful runs with blocked PRs
2. ✅ **Updated script documentation** - Exit codes clearly documented
3. ✅ **Incident report created** - Root cause and resolution documented

### Recommended

1. **Exit code policy for automation scripts**:
   - Exit 0: Success (including expected informational states)
   - Exit 1-99: Reserved for script-specific non-fatal conditions
   - Exit 100+: Fatal errors only
   - Document exit codes in script header

2. **Workflow design patterns**:
   - Use dedicated steps for informational alerts (blocked PRs)
   - Reserve `if: failure()` for actual errors
   - Consider `continue-on-error: true` with explicit exit code checks
   - Separate monitoring from failure handling

3. **Testing improvements**:
   - Test workflows with various exit code scenarios
   - Validate alert creation logic separately from failure logic
   - Add integration tests for false-positive scenarios

4. **Monitoring enhancements**:
   - Track false-positive alert rate
   - Add workflow health dashboard
   - Monitor exit code distribution across runs

## Lessons Learned

### What went well

- Automated issue creation via workflow failure handler (detected problem quickly)
- Clear logging in PR maintenance script (identified 6 blocked PRs correctly)
- Workflow executed all tasks successfully despite false-positive alert
- Separate step for blocked PR alerts already existed (good design)

### What could be improved

- Exit code semantics should align with GitHub Actions expectations
- Distinguish between "informational" states and "error" states
- Test workflow behavior with various exit codes before deployment
- Document exit code contract in script headers

### Action items

| Action | Owner | Priority | Status |
|--------|-------|----------|--------|
| Update exit code policy documentation | DevOps | P1 | ✅ Done |
| Add workflow testing guide for exit codes | DevOps | P2 | TODO |
| Review other scripts for similar exit code issues | DevOps | P2 | TODO |
| Add exit code testing to CI | DevOps | P3 | TODO |

## References

- GitHub Issue: #[TBD] - "[ALERT] PR Maintenance Workflow Failed"
- Workflow file: `.github/workflows/pr-maintenance.yml`
- Script file: `scripts/Invoke-PRMaintenance.ps1`
- Workflow run: https://github.com/rjmurillo/ai-agents/actions/runs/20474739125
- Logs: See workflow run artifacts

## Cost Impact

**No cost impact**: Workflow executed successfully and completed in 16 seconds (normal).

---

*Incident report template v1.0*
*DevOps Agent - 2025-12-24*
