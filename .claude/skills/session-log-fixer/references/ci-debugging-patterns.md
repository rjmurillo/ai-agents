# CI Debugging Patterns for Session Protocol Validation

Patterns extracted from real CI debugging sessions.

**Note**: Replace `$Repo` in examples with your repository in `owner/repo` format (e.g., `rjmurillo/ai-agents`). You can infer this from `git remote get-url origin`.

---

## Job-Level Diagnostics

### Check All Jobs in a Run

```powershell
$Repo = "owner/repo"  # Set to your repository (e.g., rjmurillo/ai-agents)
gh api /repos/$Repo/actions/runs/$RunId/jobs --jq '.jobs[] | {name: .name, status: .status, conclusion: .conclusion}'
```

### Find Stuck or Incomplete Jobs

```powershell
gh run view $RunId --json jobs --jq '.jobs[] | select(.status != "completed") | {name: .name, status: .status}'
```

### Check Runner Assignment

```powershell
gh api /repos/$Repo/actions/runs/$RunId/jobs --jq '.jobs[] | {name: .name, status: .status, runner: .runner_name}'
```

A `null` runner_name indicates the job hasn't been assigned to a runner yet.

---

## Common Stuck Job Patterns

### 1. Runner Queue Congestion

**Symptoms:**

- Jobs stuck in `queued` status for 10+ minutes
- `runner_name: null` in job details
- ARM runners (`ubuntu-24.04-arm`) more prone to congestion

**Diagnosis:**

```powershell
gh api /repos/$Repo/actions/runs/$RunId/jobs --jq '.jobs[] | select(.status == "queued") | {name: .name, runner: .runner_name}'
```

**Resolution:**
Wait for runners to become available. If persistent, check GitHub Status.

### 2. Skipped Aggregate Job

**Symptoms:**

- Individual jobs complete successfully
- `Aggregate Results` shows as `skipped`
- Required check never passes

**Diagnosis:**

```powershell
gh api /repos/$Repo/actions/runs/$RunId/jobs --jq '.jobs[] | select(.name | contains("Aggregate")) | {name: .name, status: .status, conclusion: .conclusion}'
```

**Common Causes:**

- Workflow `if:` condition not met
- Premature job dependency resolution
- Path filter excluded all files

### 3. Matrix Job Output Issues

**Symptoms:**

- Matrix jobs complete but downstream job fails
- Outputs from only one matrix leg visible

**Root Cause:**
Matrix job outputs only expose ONE matrix leg's outputs to downstream jobs.

**Resolution:**
Use artifacts instead of outputs for reliable handoff between jobs.

---

## Diagnostic Command Reference

| Purpose | Command |
|---------|---------|
| Run overview | `gh run view $RunId` |
| All jobs status | `gh api .../actions/runs/$RunId/jobs --jq '.jobs[]...'` |
| Failed jobs only | `...--jq '.jobs[] \| select(.conclusion == "failure")'` |
| Incomplete jobs | `...--jq '.jobs[] \| select(.status != "completed")'` |
| Workflow logs | `gh run view $RunId --log 2>&1 \| head -100` |
| Specific job log | `gh run view $RunId --log --job $JobId` |

---

## Session Protocol Validation Specific

### Check Aggregate Results Status

```powershell
$runId = "20608909597"  # Example run ID
gh api /repos/$Repo/actions/runs/$runId/jobs --jq '.jobs[] | select(.name | contains("Aggregate")) | {name: .name, status: .status, conclusion: .conclusion}'
```

### Find NON_COMPLIANT Verdict

The `Aggregate Results` job aggregates verdicts from validation jobs. Check artifacts:

```powershell
gh run download $RunId --dir $env:TEMP/session-artifacts-$RunId
Get-ChildItem -Path "$env:TEMP/session-artifacts-$RunId" -Filter "*-verdict.txt" -Recurse | ForEach-Object {
    Write-Host "--- $($_.Name) ---"
    Get-Content $_.FullName
}
```

---

## Integration with diagnose.ps1

The `diagnose.ps1` script automates these patterns. Enhancements to consider:

1. **Job-level status**: Show individual job statuses, not just run-level
2. **Runner check**: Identify jobs waiting for runners
3. **Stuck detection**: Flag jobs queued for >10 minutes
4. **Skipped aggregate detection**: Alert when Aggregate Results is skipped

---

## Source

Patterns extracted from Session 001 transcript (2025-12-31) debugging PR 534 stuck checks.
