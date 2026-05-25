---
name: pipeline-validator
version: 1.0.0
model: claude-sonnet-4-6
description: Discovers, triggers, and monitors Azure DevOps pipelines (PR, Buddy Build, Buddy Release) for the current repo and branch. Auto-diagnoses failures from build logs, applies fixes, commits, pushes, and re-triggers until all pipelines pass or max retries reached. Validates PR existence and description completeness. Designed to be invoked automatically after any change-making skill creates a PR.
license: MIT
---

# Pipeline Validator

Discovers, triggers, and monitors Azure DevOps pipelines for the current repository and branch. When a pipeline fails, it diagnoses the issue from build logs, applies a fix, commits, pushes, and re-triggers — repeating until all pipelines succeed or a max retry limit is reached. Validates PR existence and description quality before starting pipeline runs.

This skill is designed to be **automatically invoked** after any change-making skill (e.g., `windows-image-updater`, `dotnet10-upgrade`) creates a PR. It is also independently invocable for validating any branch/PR.

---

## Triggers

- `validate pipelines` — Start pipeline validation for current branch
- `trigger and fix pipelines` — Full trigger-diagnose-fix loop
- `run pipeline validation` — Alternative phrasing
- `check pr pipelines` — PR-focused validation
- `monitor pipelines for {repo}` — Repo-specific trigger

## Quick Reference

| Input | Output | Duration |
|-------|--------|----------|
| Current repo + branch (auto-detected) | All pipelines green, PR description updated with links | 30-180 min |

---

## Prerequisites

### Required Tools

| Tool | Purpose | Verify |
|------|---------|--------|
| **Git** | Version control, branch detection | `git --version` |
| **Azure CLI** | Pipeline discovery, triggering, log retrieval | `az --version` |
| **Azure DevOps extension** | ADO-specific commands | `az extension show --name azure-devops` |
| **.NET SDK** | Local build verification before push | `dotnet --version` |

### Required Access

| Access | Why |
|--------|-----|
| ADO repository read/write | Push fixes, update PR |
| Pipeline trigger permission | Trigger PR/Buddy/Release pipelines |
| Build logs read access | Download and analyze failure logs |

---

## Execution Policy

- Execute every step **autonomously**. Do not ask for confirmation between pipeline triggers or retries.
- On terminal confirmation prompts: answer yes automatically.
- On pipeline failure: **do NOT stop**. Download logs, diagnose, fix, commit, push, and re-trigger.
- Only stop if you hit the max retry limit or encounter an issue you genuinely cannot fix (e.g., infrastructure outage, permissions error).

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Organization | `https://microsoft.visualstudio.com` | Azure DevOps organization URL |
| Project | `Windows Defender` | Azure DevOps project |
| Max retries per pipeline | 3 | Maximum fix-and-retry attempts per pipeline |
| Poll interval | 10 minutes (600 seconds) | Time between pipeline status checks |
| Max polls per run | 18 (3 hours) | Maximum polling attempts before timeout |

---

## Process

### Step 1: Auto-Detect Context

**Purpose:** Gather all required context from the current working directory and git state.

```powershell
# Detect repo name
$repoName = (Get-Item .).Name
Write-Host "Repo: $repoName"

# Detect current branch
$branch = git branch --show-current
Write-Host "Branch: $branch"

# Detect active PR for this branch
$prs = az repos pr list --source-branch "refs/heads/$branch" --organization <org-url> --project "<project>" --status active --output json | ConvertFrom-Json
if ($prs.Count -gt 0) {
    $prId = $prs[0].pullRequestId
    Write-Host "Active PR found: #$prId"
} else {
    Write-Host "No active PR found for branch $branch"
}
```

**Decision:**

- **PR found:** Proceed to Step 2 (Validate PR).
- **No PR found:** Report to user — a PR must exist before pipeline validation. The calling skill should have created one.

**Verification:**

- [ ] Repo name detected
- [ ] Branch name detected
- [ ] PR ID detected (or user notified)

---

### Step 2: Validate PR

**Purpose:** Ensure the PR exists and has a meaningful description before triggering pipelines.

```powershell
# Get PR details
$prDetails = az repos pr show --id $prId --organization <org-url> --project "<project>" --output json | ConvertFrom-Json
Write-Host "PR Title: $($prDetails.title)"
Write-Host "PR Status: $($prDetails.status)"
Write-Host "PR Draft: $($prDetails.isDraft)"
Write-Host "Target Branch: $($prDetails.targetRefName)"
```

#### PR Description Validation

Check that the PR description contains these required sections:

| Section | Required | Check |
|---------|----------|-------|
| **Summary** | Yes | Description contains `## Summary` with non-empty content |
| **Changes** | Yes | Description contains `## Changes` with at least one bullet point |
| **Validation** | Yes | Description contains `## Validation` with checklist items |

**Note:** Missing description sections are a warning, not a blocker. The skill will proceed but report the gap.

**Verification:**

- [ ] PR exists and is accessible
- [ ] PR description has Summary section (warning if missing)
- [ ] PR description has Changes section (warning if missing)
- [ ] PR description has Validation section (warning if missing)

---

### Step 3: Discover Pipelines

**Purpose:** Find all pipelines associated with this repository and classify them by type.

```powershell
$allPipelines = (az pipelines list --organization <org-url> --project "<project>" --output json | ConvertFrom-Json) | Where-Object { $_.name.Contains($repoName) }
$allPipelines | ForEach-Object { Write-Host "  [$($_.id)] $($_.name)" }
```

#### Pipeline Classification

Match each pipeline to its type by name pattern (case-insensitive):

| Type | Match Rule | Priority |
|------|-----------|----------|
| **PR build** | Name contains `PR` or `PullRequest` | 1 (run first) |
| **Buddy build** | Name contains `Buddy` and does NOT contain `Release` | 2 (run second) |
| **Buddy release** | Name contains `Buddy` AND `Release` | 3 (run third) |

**Decision:**

- **No pipelines found at all:** Report and stop — the repo may not have CI pipelines configured.
- **Some found, some missing:** Proceed with the ones available in order: PR → Buddy Build → Buddy Release, skipping missing ones.

**Verification:**

- [ ] At least one pipeline discovered
- [ ] Pipeline types correctly classified

---

### Step 4: Run Pipeline Sequence

**Purpose:** Execute pipelines in order: **PR Build → Buddy Build → Buddy Release**. For each pipeline, follow the trigger-poll-diagnose-fix loop.

#### 4.1 Idempotent State Check

Before triggering, check for existing runs on this branch to avoid unnecessary re-runs:

| State | Action |
|-------|--------|
| No runs on this branch | Trigger a new run |
| `completed` + `succeeded` (current commit) | **Skip** — already passed. Move to next pipeline |
| `completed` + `succeeded` (old commit) | Trigger a new run — success was for different code |
| `inProgress` or `notStarted` | **Resume polling** with that run ID |
| `completed` + `failed` | Trigger a fresh run |

```powershell
# Verify the successful run is for the current commit
$currentSha = git rev-parse HEAD
if ($recentRun -and $recentRun[0].status -eq "completed" -and $recentRun[0].result -eq "succeeded") {
    if ($recentRun[0].sourceVersion -eq $currentSha) {
        Write-Host "✓ Pipeline already succeeded for current commit. Skipping."
    } else {
        Write-Host "⚠ Last success was for a different commit. Triggering new run."
    }
}
```

#### 4.2 Trigger Pipeline

```powershell
$run = az pipelines run --id <pipeline-id> --branch <branch> --organization <org-url> --project "<project>" --output json | ConvertFrom-Json
$runId = $run.id
Write-Host "Triggered <pipeline-type>. Run ID: $runId"
```

#### 4.3 Poll Until Complete

```powershell
$pollCount = 0
$maxPolls = 18
do {
    Start-Sleep -Seconds 600
    $pollCount++
    $status = az pipelines runs show --id $runId --organization <org-url> --project "<project>" --query "{status:status, result:result}" --output json | ConvertFrom-Json
    Write-Host "Poll $pollCount/$maxPolls — Status: $($status.status), Result: $($status.result)"
} while ($status.status -ne "completed" -and $pollCount -lt $maxPolls)
```

#### 4.4 Evaluate Result

| Result | Action |
|--------|--------|
| `succeeded` | Move to next pipeline |
| Timeout (max polls reached) | Report the run URL and stop. User can re-invoke later |
| `failed` | Enter **Step 5: Diagnose and Fix Loop** |

**Verification (per pipeline):**

- [ ] Pipeline triggered (or skipped if already succeeded)
- [ ] Pipeline completed within timeout
- [ ] Pipeline result is `succeeded`

---

### Step 5: Diagnose and Fix Loop

**Purpose:** When a pipeline fails, download logs, diagnose the failure, apply a code fix, commit, push, and re-trigger. Maximum 3 retries per pipeline.

#### 5.1 Download and Analyze Build Logs

```powershell
# Get the timeline to find failed tasks
$timeline = az devops invoke --area build --resource timeline --route-parameters buildId=$runId project="<project>" --organization <org-url> --output json | ConvertFrom-Json

# Find failed records
$failedRecords = $timeline.records | Where-Object { $_.result -eq "failed" }
$failedRecords | ForEach-Object {
    Write-Host "FAILED: $($_.name) — $($_.type)"
}
```

#### 5.2 Diagnose the Failure

Analyze error messages against known patterns. See [references/error-patterns.md](references/error-patterns.md) for the full pattern catalog.

**Quick Reference — Error-to-Fix Map:**

| Error Pattern | Auto-Fixable? | Fix Action |
|---------------|---------------|------------|
| `error CS****` (compile error) | ✅ | Fix source code at the reported file:line |
| `TreatWarningsAsErrors` | ✅ | Suppress the specific warning code, or set to `false` |
| `error NU****` (NuGet error) | ✅ | Fix package version or source config |
| `File not found` / path reference | ✅ | Correct the file reference in YAML or config |
| `Assembly load failure` | ✅ | Fix assembly name / topology name |
| `Test failure` | ✅/⚠️ | Fix code or update test; re-trigger if flaky |
| `Subscription key conflict` | ✅ | Rename generic subscription key |
| `YAML syntax error` | ✅ | Fix YAML syntax |
| `Permission / 403` | ❌ | Report to user — cannot auto-fix |
| `Infrastructure / transient` | ⚠️ | Retry without code changes |

#### 5.3 Apply the Fix

1. **Identify** the file(s) to change from the error output.
2. **Read** the file(s) to understand current state.
3. **Edit** the file(s) to fix the issue.
4. **Verify locally** if possible:

   ```powershell
   dotnet build 2>&1 | Select-Object -Last 20
   ```

#### 5.4 Commit and Push the Fix

```powershell
git add -A
git commit -m "fix: <brief description of what was fixed>"
git push
```

**Commit message conventions for auto-fixes:**

- `fix: set TreatWarningsAsErrors to false in pipeline YAML`
- `fix: correct RolloutSpec path reference in buddy.release.yml`
- `fix: rename subscription key from PrimarySub to <ServiceName>Sub`
- `fix: resolve NuGet package version for <PackageName>`
- `fix: suppress warning <code> in <file>`

#### 5.5 Re-Trigger the Pipeline

Go back to Step 4.2 and trigger the same pipeline again. Increment the retry counter.

If retry count exceeds the max (3), report all attempted fixes and the persistent failure, then stop and ask user for help.

---

### Step 6: Handle Buddy Release Auto-Trigger

**Purpose:** The Buddy Release pipeline may auto-trigger after a successful Buddy Build.

After Buddy Build succeeds, wait 5 minutes and check:

```powershell
Write-Host "Waiting 5 minutes for automatic Buddy Release trigger..."
Start-Sleep -Seconds 300

$recentRelease = az pipelines runs list --pipeline-ids <buddy-release-pipeline-id> --branch <branch> --organization <org-url> --project "<project>" --top 1 --output json | ConvertFrom-Json
```

- **Run exists** that started after Buddy Build completed → It was auto-triggered. Use that run ID and poll.
- **No run triggered** → Trigger it manually (Step 4.2).

---

### Step 7: Update PR Description

**Purpose:** After all pipelines pass, update the PR description with pipeline run links and results.

Update the `## Validation` section in the PR description to replace placeholder `[ ]` checkboxes with `[x]` and add pipeline run URLs with links.

---

### Step 8: Final Report

**Purpose:** Summarize the entire validation run for the user.

Report these items:

| Item | Detail |
|------|--------|
| **Branch** | The branch that was validated |
| **PR** | PR ID and URL |
| **PR Description** | Complete / missing sections noted |
| **PR Build** | Run ID, URL, result, retry count |
| **Buddy Build** | Run ID, URL, result, retry count |
| **Buddy Release** | Run ID, URL, result, retry count, auto-triggered or manual |
| **Fixes Applied** | List of commits with descriptions |
| **Final Status** | ✅ All passed / ⚠️ Partial failure / ❌ Stopped |

If all pipelines passed:

```
Consider marking the PR as ready for review.
```

---

## Integration with Other Skills

This skill is designed to be called automatically by other skills after they create a PR. To integrate:

### For Skill Authors

Add this section at the end of your skill's PR creation phase:

```markdown
### Post-Change Validation

After the PR is created, invoke the **pipeline-validator** skill to validate all pipelines pass.
The pipeline-validator will automatically:
1. Find the PR for the current branch
2. Validate the PR description has required sections (Summary, Changes, Validation)
3. Discover and trigger all associated pipelines (PR Build → Buddy Build → Buddy Release)
4. Auto-diagnose and fix any pipeline failures (up to 3 retries per pipeline)
5. Update the PR description with pipeline run links
6. Report final status
```

### Currently Integrated Skills

| Skill | Integration Point |
|-------|------------------|
| `windows-image-updater` | After Phase 4 PR creation |
| `dotnet10-upgrade` | After Phase 4 PR creation |

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Fixing all errors at once | One fix often resolves many downstream errors | Fix the FIRST error, rebuild, repeat |
| Ignoring idempotent checks | Wastes pipeline runs on already-passed code | Always check existing runs before triggering |
| Manually editing pipeline YAML to fix failures | Generated YAML gets overwritten by ConfigGen | Fix the source (package versions, code, config) |
| Retrying indefinitely | Wastes time on unfixable issues | Max 3 retries, then ask user |
| Skipping local build verification | Pushes broken code, wastes pipeline runs | Always `dotnet build` locally before pushing a fix |
| Triggering all pipelines simultaneously | Later pipelines depend on earlier ones | Sequential: PR → Buddy Build → Buddy Release |

---

## Verification Checklist

After complete execution:

- [ ] PR exists and has description with Summary, Changes, Validation sections
- [ ] PR Build pipeline passes
- [ ] Buddy Build pipeline passes
- [ ] Buddy Release pipeline passes
- [ ] PR description updated with all pipeline run links
- [ ] Final status reported to user

---

## Aborting / Rollback

| Failed At | Action |
|-----------|--------|
| Pipeline keeps failing after max retries | Report to user with all logs and attempted fixes |
| Permission / access denied | Report to user — cannot self-fix |
| Infrastructure outage | Report to user, suggest retrying later |
| Fix introduced new failures | `git revert HEAD` to undo the fix, report to user |

---

## Extension Points

1. **Organization/Project:** Change defaults for non-MDE repos
2. **Pipeline patterns:** Add new name patterns as team naming conventions evolve
3. **Error patterns:** Add new diagnostic patterns to `references/error-patterns.md`
4. **Retry limits:** Adjust per-pipeline retry limits for different confidence levels
5. **Notification:** Add Teams/Slack notification when all pipelines pass
6. **Multi-repo batch:** Extend to validate pipelines across multiple repos

---

## References

- [Error Patterns Catalog](references/error-patterns.md) — Complete error diagnosis patterns with fixes
- [Azure DevOps CLI — Pipelines](https://learn.microsoft.com/en-us/cli/azure/pipelines)
- [Azure DevOps CLI — Build logs](https://learn.microsoft.com/en-us/cli/azure/devops)
