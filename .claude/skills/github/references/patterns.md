# Common Patterns

Reusable patterns for GitHub CLI operations.

---

## Owner/Repo Inference

All scripts auto-infer from `git remote` when `-Owner` and `-Repo` are omitted.

---

## Idempotency with Markers

Use `-Marker` to prevent duplicate comments:

```powershell
# First call: posts comment with <!-- AI-TRIAGE --> marker
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "..." -Marker "AI-TRIAGE"

# Second call: exits with code 5 (already exists)
```

---

## Body from File

For multi-line content, use `-BodyFile` to avoid escaping issues.

---

## Thread Management Workflow

```powershell
# 1. Get unresolved threads
$threads = pwsh -NoProfile scripts/pr/Get-PRReviewThreads.ps1 -PullRequest 50 -UnresolvedOnly | ConvertFrom-Json

# 2. Reply to each thread using thread ID (recommended for GraphQL)
foreach ($t in $threads.Threads) {
    pwsh -NoProfile scripts/pr/Add-PRReviewThreadReply.ps1 -ThreadId $t.ThreadId -Body "Fixed." -Resolve
}

# 3. Or reply using comment ID (REST API)
foreach ($t in $threads.Threads) {
    pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId $t.FirstCommentId -Body "Fixed."
}
pwsh -NoProfile scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

# 4. Merge
pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch
```

---

## Merge Readiness Check

```powershell
# Full merge readiness check
$ready = pwsh -NoProfile scripts/pr/Test-PRMergeReady.ps1 -PullRequest 50 | ConvertFrom-Json

if ($ready.CanMerge) {
    pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch
} else {
    Write-Host "Cannot merge. Reasons:"
    $ready.Reasons | ForEach-Object { Write-Host "  - $_" }

    # Check specific blockers
    if ($ready.UnresolvedThreads -gt 0) {
        Write-Host "Unresolved threads: $($ready.UnresolvedThreads)"
    }
    if (-not $ready.CIPassing) {
        Write-Host "Failed checks: $($ready.FailedChecks -join ', ')"
        Write-Host "Pending checks: $($ready.PendingChecks -join ', ')"
    }
}
```

---

## Auto-Merge Workflow

```powershell
# Check current readiness (threads must be resolved, but CI can be pending)
$ready = pwsh -NoProfile scripts/pr/Test-PRMergeReady.ps1 -PullRequest 50 -IgnoreCI | ConvertFrom-Json

if ($ready.CanMerge) {
    # Enable auto-merge - PR will merge when CI passes
    pwsh -NoProfile scripts/pr/Set-PRAutoMerge.ps1 -PullRequest 50 -Enable -MergeMethod SQUASH
    Write-Host "Auto-merge enabled. PR will merge when all checks pass."
} else {
    Write-Host "Cannot enable auto-merge: $($ready.Reasons -join '; ')"
}
```

---

## PR Enumeration Workflow

```powershell
# Get all open PRs targeting main
$prs = pwsh -NoProfile scripts/pr/Get-PullRequests.ps1 -State open -Base main | ConvertFrom-Json

# Check each PR for merge readiness
foreach ($pr in $prs) {
    $ready = pwsh -NoProfile scripts/pr/Test-PRMergeReady.ps1 -PullRequest $pr.number | ConvertFrom-Json
    if ($ready.CanMerge) {
        Write-Host "PR #$($pr.number) is ready to merge"
        pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest $pr.number -Strategy squash -DeleteBranch
    }
}
```

---

## Pre-Review Check

Always check if PR is merged before starting review work:

```powershell
$result = pwsh -NoProfile scripts/pr/Test-PRMerged.ps1 -PullRequest 50
if ($LASTEXITCODE -eq 1) {
    Write-Host "PR already merged, skipping review"
    exit 0
}
```

---

## Batch Reactions

Use batch mode for 88% faster acknowledgment of multiple comments:

```powershell
# Get all review comment IDs
$comments = pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50 | ConvertFrom-Json
$ids = $comments | ForEach-Object { $_.id }

# Batch acknowledge (saves ~1.2s per comment vs. individual calls)
$result = pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId $ids -Reaction "eyes" | ConvertFrom-Json

# Check results
Write-Host "Acknowledged $($result.Succeeded)/$($result.TotalCount) comments"
if ($result.Failed -gt 0) {
    Write-Host "Failed reactions: $($result.Results | Where-Object { -not $_.Success } | ForEach-Object { $_.CommentId })"
}
```

---

## CI Check Verification

```powershell
# Quick check - get current status
$checks = pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 | ConvertFrom-Json

if ($checks.AllPassing) {
    Write-Host "All CI checks passing"
} elseif ($checks.FailedCount -gt 0) {
    Write-Host "BLOCKED: $($checks.FailedCount) check(s) failed"
    $checks.Checks | Where-Object { $_.Conclusion -notin @('SUCCESS', 'NEUTRAL', 'SKIPPED', $null) } | ForEach-Object {
        Write-Host "  - $($_.Name): $($_.DetailsUrl)"
    }
    exit 1
} else {
    Write-Host "Pending: $($checks.PendingCount) check(s) still running"
}

# Poll until all checks complete (or timeout)
$checks = pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 -Wait -TimeoutSeconds 600 | ConvertFrom-Json

if ($LASTEXITCODE -eq 7) {
    Write-Host "Timeout waiting for checks"
    exit 1
}

if ($checks.AllPassing) {
    pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch
}
```

---

## Integration Pattern

```powershell
# Chain operations with error handling
$pr = pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 | ConvertFrom-Json
if (-not $pr.Success) { throw "Failed to get PR context" }

$checks = pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 -Wait | ConvertFrom-Json
if ($checks.AllPassing) {
    pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash
}
```
