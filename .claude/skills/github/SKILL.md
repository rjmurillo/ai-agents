---
name: github
description: |
  GitHub CLI operations for PRs, Issues, Labels, Milestones, Comments, and Reactions.
  Use when Claude needs to: (1) Get PR context, diff, or changed files, (2) Reply to
  PR review comments preserving threads, (3) Post idempotent issue comments, (4) Apply
  or create labels, (5) Assign milestones, (6) Add reactions to comments, (7) Close or
  merge PRs, (8) Resolve review threads, (9) Synthesize context for Copilot assignment,
  (10) Create new issues or PRs with validation.
  Do NOT use for: raw git operations, GitHub Actions workflow editing, repository settings.
allowed-tools: Bash(pwsh:*), Bash(gh api:*), Bash(gh pr:*), Bash(gh issue:*), Read, Write, Grep, Glob
metadata:
  generator:
    keep_headings:
      - Decision Tree
      - Script Reference
      - Quick Examples
      - Common Patterns
      - Output Format
      - See Also
---

# GitHub Skill

Use these scripts instead of raw `gh` commands for consistent error handling and structured output.

## Decision Tree

```text
Need GitHub data?
├─ PR info/diff → Get-PRContext.ps1
├─ CI check status → Get-PRChecks.ps1
├─ Review comments → Get-PRReviewComments.ps1
├─ Review threads → Get-PRReviewThreads.ps1
├─ Unique reviewers → Get-PRReviewers.ps1
├─ Unaddressed bot comments → Get-UnaddressedComments.ps1
├─ PR merged check → Test-PRMerged.ps1
├─ Copilot follow-up PRs → Detect-CopilotFollowUpPR.ps1
├─ Issue info → Get-IssueContext.ps1
├─ Merge readiness check → Test-PRMergeReady.ps1
└─ Need to take action?
   ├─ Create issue → New-Issue.ps1
   ├─ Create PR → New-PR.ps1
   ├─ Reply to review → Post-PRCommentReply.ps1
   ├─ Reply to thread (GraphQL) → Add-PRReviewThreadReply.ps1
   ├─ Comment on issue → Post-IssueComment.ps1
   ├─ Add reaction → Add-CommentReaction.ps1
   ├─ Apply labels → Set-IssueLabels.ps1
   ├─ Set milestone → Set-IssueMilestone.ps1
   ├─ Resolve threads → Resolve-PRReviewThread.ps1
   ├─ Process AI triage → Invoke-PRCommentProcessing.ps1
   ├─ Assign Copilot → Invoke-CopilotAssignment.ps1
   ├─ Enable/disable auto-merge → Set-PRAutoMerge.ps1
   ├─ Close PR → Close-PR.ps1
   └─ Merge PR → Merge-PR.ps1
```

## Script Reference

### PR Operations (`scripts/pr/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-PRContext.ps1` | PR metadata, diff, files | `-PullRequest`, `-IncludeChangedFiles`, `-IncludeDiff` |
| `Get-PRChecks.ps1` | CI check status, polling | `-PullRequest`, `-Wait`, `-TimeoutSeconds`, `-RequiredOnly` |
| `Get-PRReviewComments.ps1` | Paginated review comments | `-PullRequest`, `-IncludeIssueComments` |
| `Get-PRReviewThreads.ps1` | Thread-level review data | `-PullRequest`, `-UnresolvedOnly` |
| `Get-PRReviewers.ps1` | Enumerate unique reviewers | `-PullRequest`, `-ExcludeBots` |
| `Get-UnaddressedComments.ps1` | Bot comments needing attention | `-PullRequest` |
| `Get-UnresolvedReviewThreads.ps1` | Unresolved thread IDs | `-PullRequest` |
| `Test-PRMerged.ps1` | Check if PR is merged | `-PullRequest` |
| `Detect-CopilotFollowUpPR.ps1` | Detect Copilot follow-up PRs | `-PRNumber`, `-Owner`, `-Repo` |
| `Post-PRCommentReply.ps1` | Thread-preserving replies | `-PullRequest`, `-CommentId`, `-Body` |
| `Add-PRReviewThreadReply.ps1` | Reply to thread by ID (GraphQL) | `-ThreadId`, `-Body`, `-Resolve` |
| `Resolve-PRReviewThread.ps1` | Mark threads resolved | `-ThreadId` or `-PullRequest -All` |
| `Unresolve-PRReviewThread.ps1` | Mark threads unresolved | `-ThreadId` or `-PullRequest -All` |
| `Get-ThreadById.ps1` | Get single thread by ID | `-ThreadId` |
| `Get-ThreadConversationHistory.ps1` | Full thread comment history | `-ThreadId`, `-IncludeMinimized` |
| `Test-PRMergeReady.ps1` | Check merge readiness | `-PullRequest`, `-IgnoreCI`, `-IgnoreThreads` |
| `Set-PRAutoMerge.ps1` | Enable/disable auto-merge | `-PullRequest`, `-Enable`/`-Disable`, `-MergeMethod` |
| `Invoke-PRCommentProcessing.ps1` | Process AI triage output | `-PRNumber`, `-Verdict`, `-FindingsJson` |
| `New-PR.ps1` | Create PR with validation | `-Title`, `-Body`, `-Base` |
| `Close-PR.ps1` | Close PR with comment | `-PullRequest`, `-Comment` |
| `Merge-PR.ps1` | Merge with strategy | `-PullRequest`, `-Strategy`, `-DeleteBranch`, `-Auto` |

### Issue Operations (`scripts/issue/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-IssueContext.ps1` | Issue metadata | `-Issue` |
| `New-Issue.ps1` | Create new issue | `-Title`, `-Body`, `-Labels` |
| `Set-IssueLabels.ps1` | Apply labels (auto-create) | `-Issue`, `-Labels`, `-Priority` |
| `Set-IssueMilestone.ps1` | Assign milestone | `-Issue`, `-Milestone` |
| `Post-IssueComment.ps1` | Comments with idempotency | `-Issue`, `-Body`, `-Marker` |
| `Invoke-CopilotAssignment.ps1` | Synthesize context for Copilot | `-IssueNumber`, `-WhatIf` |

### Reactions (`scripts/reactions/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Add-CommentReaction.ps1` | Add emoji reactions (batch support) | `-CommentId[]`, `-Reaction`, `-CommentType` |

## Quick Examples

```powershell
# Get PR with changed files
pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

# Check if PR is merged before starting work
pwsh -NoProfile scripts/pr/Test-PRMerged.ps1 -PullRequest 50

# Get CI check status
pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50

# Wait for CI checks to complete (timeout 10 minutes)
pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 -Wait -TimeoutSeconds 600

# Get only required checks
pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 -RequiredOnly

# Detect Copilot follow-up PRs
pwsh -NoProfile scripts/pr/Detect-CopilotFollowUpPR.ps1 -PRNumber 50

# Reply to review comment (thread-preserving)
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed."

# Resolve all unresolved review threads
pwsh -NoProfile scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

# Reply to review thread by thread ID (GraphQL)
pwsh -NoProfile scripts/pr/Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -Body "Fixed."

# Reply to thread and resolve in one operation
pwsh -NoProfile scripts/pr/Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -Body "Fixed." -Resolve

# Check if PR is ready to merge (threads resolved, CI passing)
pwsh -NoProfile scripts/pr/Test-PRMergeReady.ps1 -PullRequest 50

# Enable auto-merge with squash
pwsh -NoProfile scripts/pr/Set-PRAutoMerge.ps1 -PullRequest 50 -Enable -MergeMethod SQUASH

# Disable auto-merge
pwsh -NoProfile scripts/pr/Set-PRAutoMerge.ps1 -PullRequest 50 -Disable

# Create new issue
pwsh -NoProfile scripts/issue/New-Issue.ps1 -Title "Bug: Login fails" -Body "Steps..." -Labels "bug,P1"

# Create PR with validation
pwsh -NoProfile scripts/pr/New-PR.ps1 -Title "feat: Add feature" -Body "Description"

# Close PR with comment
pwsh -NoProfile scripts/pr/Close-PR.ps1 -PullRequest 50 -Comment "Superseded by #51"

# Merge PR with squash
pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch

# Post idempotent comment (prevents duplicates)
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"

# Add reaction to single comment
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"

# Add reactions to multiple comments (batch - 88% faster)
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId @(123, 456, 789) -Reaction "eyes"

# Acknowledge all comments on a PR (batch)
$ids = pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 42 | ConvertFrom-Json | ForEach-Object { $_.id }
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId $ids -Reaction "eyes"
```

## Common Patterns

### Owner/Repo Inference

All scripts auto-infer from `git remote` when `-Owner` and `-Repo` are omitted.

### Idempotency with Markers

Use `-Marker` to prevent duplicate comments:

```powershell
# First call: posts comment with <!-- AI-TRIAGE --> marker
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "..." -Marker "AI-TRIAGE"

# Second call: exits with code 5 (already exists)
```

### Body from File

For multi-line content, use `-BodyFile` to avoid escaping issues.

### Thread Management Workflow

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

### Merge Readiness Check

Check all conditions before merging:

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

### Auto-Merge Workflow

Enable auto-merge for PRs that meet all requirements when checks pass:

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

### Pre-Review Check

Always check if PR is merged before starting review work:

```powershell
$result = pwsh -NoProfile scripts/pr/Test-PRMerged.ps1 -PullRequest 50
if ($LASTEXITCODE -eq 1) {
    Write-Host "PR already merged, skipping review"
    exit 0
}
```

### Batch Reactions

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

### CI Check Verification

Check CI status before claiming PR review complete:

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
```

Wait for checks to complete before merge:

```powershell
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

### Copilot Directive Prompts

GitHub Copilot is **amnesiac**. It has no memory of the codebase, PR context, or prior work. Every @copilot directive must be a complete, self-contained prompt.

**Before posting any @copilot directive, use the prompt-builder agent to generate a high-quality prompt.**

#### Workflow

1. Gather context (PR diff, review comments, codebase patterns)
2. Invoke prompt-builder to synthesize a comprehensive prompt
3. Post the generated prompt via issue comment or PR comment reply

```powershell
# Step 1: Gather context
$pr = pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles | ConvertFrom-Json
$threads = pwsh -NoProfile scripts/pr/Get-UnresolvedReviewThreads.ps1 -PullRequest 50 | ConvertFrom-Json

# Step 2: Use prompt-builder agent to generate the directive
# Pass context to prompt-builder, which will create an actionable, specific prompt

# Step 3: Post the generated prompt
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "$generatedPrompt"
# OR for PR comment reply:
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123 -Body "$generatedPrompt"
```

#### Prompt Quality Requirements

Copilot prompts MUST include:

- **Specific file paths**: Copilot cannot infer which files to modify
- **Exact requirements**: Use imperative language (MUST, WILL, NEVER)
- **Success criteria**: Define what "done" looks like
- **Constraints**: Coding standards, patterns to follow, things to avoid
- **Context**: Relevant code snippets, error messages, or review feedback

#### Anti-patterns

```text
BAD:  "@copilot please fix this"
BAD:  "@copilot refactor the code"
BAD:  "@copilot address the review comments"

GOOD: "@copilot In src/Services/UserService.cs, refactor the GetUser method 
       to use async/await. MUST maintain the existing interface signature. 
       MUST add null checks for the userId parameter. Follow the pattern 
       in src/Services/OrderService.cs line 45-60."
```

#### When to Use Each Tool

| Scenario | Tool | Rationale |
|----------|------|-----------|
| Creating new @copilot prompt | prompt-builder | Builds from scratch with validation |
| Refining existing prompt template | prompt-optimizer | Applies research-backed improvements |
| Complex multi-step task | prompt-builder | Handles context gathering and structure |

#### Prompt-Builder Integration

The prompt-builder agent follows a structured process:

1. **Research**: Analyzes codebase patterns, README, existing code
2. **Draft**: Creates specific, imperative instructions
3. **Validate**: Tests prompt clarity through Prompt Tester persona
4. **Iterate**: Refines until success criteria are met

Invoke prompt-builder with the context you gathered:

```text
Create a @copilot prompt for:
- Task: [what Copilot should do]
- Files: [which files to modify]
- Context: [PR diff, review comments, error messages]
- Constraints: [coding standards, patterns to follow]
```

## Output Format

All scripts output structured JSON with `Success` boolean:

```powershell
$result = pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 | ConvertFrom-Json
if ($result.Success) { ... }
```

## See Also

- `references/api-reference.md`: Exit codes, API endpoints, troubleshooting
- `references/copilot-synthesis-guide.md`: Copilot context synthesis documentation
- `modules/GitHubCore.psm1`: Shared helper functions (core module)
- `.claude/agents/prompt-builder.md`: Agent for creating high-quality @copilot prompts
- `.claude/skills/prompt-engineer/SKILL.md`: Skill for optimizing existing prompts
