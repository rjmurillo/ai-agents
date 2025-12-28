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
├─ Review comments → Get-PRReviewComments.ps1
├─ Review threads → Get-PRReviewThreads.ps1
├─ Unique reviewers → Get-PRReviewers.ps1
├─ Unaddressed bot comments → Get-UnaddressedComments.ps1
├─ PR merged check → Test-PRMerged.ps1
├─ Issue info → Get-IssueContext.ps1
└─ Need to take action?
   ├─ Create issue → New-Issue.ps1
   ├─ Create PR → New-PR.ps1
   ├─ Reply to review → Post-PRCommentReply.ps1
   ├─ Comment on issue → Post-IssueComment.ps1
   ├─ Add reaction → Add-CommentReaction.ps1
   ├─ Apply labels → Set-IssueLabels.ps1
   ├─ Set milestone → Set-IssueMilestone.ps1
   ├─ Resolve threads → Resolve-PRReviewThread.ps1
   ├─ Process AI triage → Invoke-PRCommentProcessing.ps1
   ├─ Assign Copilot → Invoke-CopilotAssignment.ps1
   ├─ Close PR → Close-PR.ps1
   └─ Merge PR → Merge-PR.ps1
```

## Script Reference

### PR Operations (`scripts/pr/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-PRContext.ps1` | PR metadata, diff, files | `-PullRequest`, `-IncludeChangedFiles`, `-IncludeDiff` |
| `Get-PRReviewComments.ps1` | Paginated review comments | `-PullRequest`, `-IncludeIssueComments` |
| `Get-PRReviewThreads.ps1` | Thread-level review data | `-PullRequest`, `-UnresolvedOnly` |
| `Get-PRReviewers.ps1` | Enumerate unique reviewers | `-PullRequest`, `-ExcludeBots` |
| `Get-UnaddressedComments.ps1` | Bot comments needing attention | `-PullRequest` |
| `Get-UnresolvedReviewThreads.ps1` | Unresolved thread IDs | `-PullRequest` |
| `Test-PRMerged.ps1` | Check if PR is merged | `-PullRequest` |
| `Post-PRCommentReply.ps1` | Thread-preserving replies | `-PullRequest`, `-CommentId`, `-Body` |
| `Resolve-PRReviewThread.ps1` | Mark threads resolved | `-ThreadId` or `-PullRequest -All` |
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
| `Add-CommentReaction.ps1` | Add emoji reactions | `-CommentId`, `-Reaction`, `-CommentType` |

## Quick Examples

```powershell
# Get PR with changed files
pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

# Check if PR is merged before starting work
pwsh -NoProfile scripts/pr/Test-PRMerged.ps1 -PullRequest 50

# Reply to review comment (thread-preserving)
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed."

# Resolve all unresolved review threads
pwsh -NoProfile scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

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

# Add reaction
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"
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

# 2. Reply to each thread
foreach ($t in $threads.Threads) {
    pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId $t.FirstCommentId -Body "Fixed."
}

# 3. Resolve all threads
pwsh -NoProfile scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

# 4. Merge
pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch
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
- `modules/GitHubHelpers.psm1`: Shared helper functions
- `.claude/agents/prompt-builder.md`: Agent for creating high-quality @copilot prompts
- `.claude/skills/prompt-engineer/SKILL.md`: Skill for optimizing existing prompts