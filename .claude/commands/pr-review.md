---
allowed-tools:
  - Bash(git:*)
  - Bash(gh:*)
  - Bash(pwsh:*)
  - Task
  - Skill
  - Read
  - Write
  - Edit
  - Glob
  - Grep
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup]
description: Use when responding to PR review comments for specified pull request(s)
---

# PR Review Command

> **Note**: This command uses extended thinking (`ultrathink`) for deep PR analysis.

ultrathink

Respond to PR review comments for the specified pull request(s): $ARGUMENTS

## Context

- Current branch: !`git branch --show-current`
- Repository: !`gh repo view --json nameWithOwner -q '.nameWithOwner'`
- Authenticated as: !`gh api user -q '.login'`

## Arguments

Parse the input: `$ARGUMENTS`

| Argument | Description | Default |
|----------|-------------|---------|
| `PR_NUMBERS` | Comma-separated PR numbers (e.g., `53,141,143`) or `all-open` | Required |
| `--parallel` | Use git worktrees for parallel execution | false |
| `--cleanup` | Clean up worktrees after completion | true |

## Workflow

### Step 1: Parse and Validate PRs

For `all-open`, query: `gh pr list --state open --json number,reviewDecision`

For each PR number, validate using:

```powershell
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

Verify: PR exists, is open (state != MERGED, CLOSED), targets current repo.

**CRITICAL - Verify PR Merge State (pr-review-007-merge-state-verification)**:

Before proceeding with review work, verify PR has not been merged via GraphQL (source of truth):

```powershell
# Check merge state via Test-PRMerged.ps1
pwsh -NoProfile .claude/skills/github/scripts/pr/Test-PRMerged.ps1 -PullRequest {number}
$merged = $LASTEXITCODE -eq 1

if ($merged) {
    Write-Host "PR #{number} is already merged. Skipping review work." -ForegroundColor Yellow
    return  # Exit current script/function; caller handles iteration to next PR
}
```

**Why this matters**: `gh pr view --json state` may return stale "OPEN" for recently merged PRs, leading to wasted effort (see Issue #321, Session 85).

### Step 1.5: Comprehensive PR Status Check (REQUIRED)

Before addressing comments, gather full PR context:

**1. Review ALL Comments** (review comments + PR comments):

```powershell
# Get review threads with resolution status
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRReviewThreads.ps1 -PullRequest {number}

# Get unresolved review threads
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-UnresolvedReviewThreads.ps1 -PullRequest {number}

# Get unaddressed comments (comments without replies)
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-UnaddressedComments.ps1 -PullRequest {number}

# Get full PR context including comments
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

**2. Check Merge Eligibility with Base Branch**:

```powershell
# Get PR context including merge state
$context = pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}

# Check: $context.Mergeable should be "MERGEABLE"
# Check: $context.MergeStateStatus for conflicts

# Verify PR is not already merged
pwsh -NoProfile .claude/skills/github/scripts/pr/Test-PRMerged.ps1 -PullRequest {number}
# Exit code 0 = not merged (safe to proceed), 1 = merged (skip)
```

**3. Review ALL Failing Checks**:

```powershell
# Get all checks with conclusions using Get-PRChecks.ps1
$checks = pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest {number} | ConvertFrom-Json

if ($checks.FailedCount -gt 0) {
    Write-Host "Failed checks:"
    $checks.Checks | Where-Object { $_.Conclusion -notin @('SUCCESS', 'NEUTRAL', 'SKIPPED', $null) } | ForEach-Object {
        Write-Host "  - $($_.Name): $($_.DetailsUrl)"
    }
}

# For each failing check, investigate:
# - If session validation: Use session-log-fixer skill
# - If AI reviewer: Check for infrastructure vs code quality issues
# - If Pester tests: Run tests locally to verify
# - If linting: Run npx markdownlint-cli2 --fix
```

**Action on failures**:

| Check Type | Failure Action |
|------------|----------------|
| Session validation | Invoke `session-log-fixer` skill |
| AI reviewer (infra) | May be transient; note and continue |
| AI reviewer (code quality) | Address findings or acknowledge |
| Pester tests | Run locally, fix failures |
| Markdown lint | Run `npx markdownlint-cli2 --fix` |
| PR title validation | Update title to conventional commit format |

### Step 2: Create Worktrees (if --parallel)

For parallel execution:

```bash
branch=$(gh pr view {number} --json headRefName -q '.headRefName')
git worktree add "../worktree-pr-{number}" "$branch"
```

### Step 3: Launch Agents

**Sequential (default):**

```python
for pr in pr_numbers:
    # Pass session context path for state continuity
    session_context = f".agents/pr-comments/PR-{pr}/"
    Skill(skill="pr-comment-responder", args=f"{pr} --session-context={session_context}")
```

**Parallel (--parallel):**

```python
agents = []
for pr in pr_numbers:
    session_context = f".agents/pr-comments/PR-{pr}/"
    agent = Task(
        subagent_type="pr-comment-responder",
        prompt=f"""PR #{pr}

Session context: {session_context}

Check for existing session state before starting. If previous session exists:
1. Load existing comment map
2. Check for NEW comments only
3. Skip to verification if no new comments

Completion requires ALL criteria:
- All comments [COMPLETE] or [WONTFIX]
- No new comments after 45s wait post-commit
- All CI checks pass (including AI Quality Gate)
- Commits pushed to remote
""",
        run_in_background=True
    )
    agents.append(agent)

for agent_id in agents:
    TaskOutput(task_id=agent_id, block=True, timeout=600000)
```

### Step 4: Verify and Push

For each worktree:

```bash
cd "../worktree-pr-{number}"
if [[ -n "$(git status --short)" ]]; then
    git add .
    git commit -m "chore(pr-{number}): finalize review response session"
    git push origin "$branch"
fi
```

### Step 5: Cleanup Worktrees (if --cleanup)

```bash
cd "{main_repo}"
for pr in pr_numbers; do
    worktree_path="../worktree-pr-${pr}"
    cd "$worktree_path"
    status="$(git status --short)"
    if [[ -z "$status" ]]; then
        cd "{main_repo}"
        git worktree remove "$worktree_path"
    else
        echo "WARNING: worktree-pr-${pr} has uncommitted changes"
    fi
done
```

### Step 6: Generate Summary

Output:

```markdown
## PR Review Summary

| PR | Branch | Comments | Acknowledged | Implemented | Commit | Status |
|----|--------|----------|--------------|-------------|--------|--------|
| #53 | feat/xyz | 4 | 4 | 3 | abc1234 | COMPLETE |
| #141 | fix/auth | 7 | 7 | 5 | def5678 | COMPLETE |

### Statistics
- **PRs Processed**: N
- **Comments Reviewed**: N
- **Fixes Implemented**: N
- **Commits Pushed**: N
- **Worktrees Cleaned**: N
```

## Error Recovery

| Scenario | Action |
|----------|--------|
| PR not found | Log warning, skip PR, continue |
| Branch conflict | Log error, skip PR, continue |
| Agent timeout | Log partial status, force cleanup |
| Push rejection | Detect concurrent updates (fetch and compare remote). If no concurrent changes, retry with `--force-with-lease`; otherwise, log rejection and require manual resolution (do not force push in parallel scenarios). |
| Merge conflict | Log conflict, skip cleanup, report for manual resolution |

## Critical Constraints (MUST)

When using `--parallel` with worktrees:

1. **Worktree Isolation**: ALL changes MUST be contained within the assigned worktree
2. **Working Directory**: Agents MUST set working directory to their worktree before file operations
3. **Path Validation**: All file paths MUST be relative to worktree root
4. **Git Operations**: Git commands MUST be executed from within the worktree directory
5. **Verification Gate**: Before cleanup, verify no files were written outside worktrees

## Completion Criteria

**ALL criteria must be true before claiming PR review complete**:

| Criterion | Verification | Required |
|-----------|--------------|----------|
| All review comments addressed | Each review thread has reply + resolution | Yes |
| All PR comments acknowledged | Each PR comment has acknowledgment (reply or reaction) | Yes |
| No new comments | Re-check after 45s wait returned 0 new | Yes |
| CI checks pass | `Get-PRChecks.ps1` AllPassing = true (or failures acknowledged) | Yes |
| No unresolved threads | GraphQL query for unresolved reviewThreads = 0 | Yes |
| Merge eligible | `mergeable=MERGEABLE`, no conflicts with base | Yes |
| PR not merged | Test-PRMerged.ps1 exit code 0 | Yes |
| Commits pushed | `git status` shows "up to date with origin" | Yes |

**If ANY criterion fails**: Do NOT claim completion. The agent must loop back to address the issue.

**Failure handling by type**:

| Failure Type | Action |
|--------------|--------|
| Session validation fails | Use `session-log-fixer` skill to diagnose and fix |
| AI reviewer fails (infra) | Note as infrastructure issue; may be transient |
| AI reviewer fails (code quality) | Address findings or document acknowledgment |
| Merge conflicts | Resolve conflicts or merge base branch |
| Behind base branch | Merge base or rebase as appropriate |

### Verification Command

```powershell
# Run after each PR to verify completion
foreach ($pr in $pr_numbers) {
    Write-Host "=== PR #$pr Completion Check ==="

    # Get CI check status using skill
    $checks = pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest $pr | ConvertFrom-Json
    if (-not $checks.AllPassing) {
        $checks.Checks | Where-Object { $_.Conclusion -notin @('SUCCESS', 'NEUTRAL', 'SKIPPED') } | ForEach-Object {
            Write-Host "  FAIL: $($_.Name) - $($_.Conclusion)"
        }
    }

    # Note: reviewThreads requires GraphQL
    gh api graphql -f query="query { repository(owner: `"OWNER`", name: `"REPO`") { pullRequest(number: $pr) { reviewThreads(first: 50) { nodes { isResolved } } } } }" | ConvertFrom-Json | ForEach-Object { $_.data.repository.pullRequest.reviewThreads.nodes | Where-Object { -not $_.isResolved } }
}
```

## Thread Resolution Protocol

### Overview (pr-review-004-thread-resolution-single, pr-review-005-thread-resolution-batch)

**CRITICAL**: Replying to a review comment does NOT automatically resolve the thread. Thread resolution requires a separate GraphQL mutation.

### Single Thread Resolution (pr-review-004-thread-resolution-single)

After replying to a review comment, resolve the thread:

```powershell
# Step 1: Reply to comment
pwsh -NoProfile .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest {number} -ThreadId "PRRT_xxx" -Body "Response text"

# Step 2: Resolve thread (REQUIRED separate step)
pwsh -NoProfile .claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1 -ThreadId "PRRT_xxx"
```

**Why this matters**: Replying to a comment does NOT automatically resolve the thread. Thread resolution requires a separate GraphQL mutation. Unresolved threads block PR merge per branch protection rules.

### Batch Thread Resolution (pr-review-005-thread-resolution-batch)

For 2+ threads, use the skill with multiple thread IDs:

```powershell
# Resolve multiple threads efficiently
$threadIds = @("PRRT_xxx", "PRRT_yyy", "PRRT_zzz")
foreach ($threadId in $threadIds) {
    pwsh -NoProfile .claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1 -ThreadId $threadId
}

# Or use GraphQL batch mutation for maximum efficiency (1 API call)
gh api graphql -f query='
mutation {
  t1: resolveReviewThread(input: {threadId: "PRRT_xxx"}) { thread { id isResolved } }
  t2: resolveReviewThread(input: {threadId: "PRRT_yyy"}) { thread { id isResolved } }
  t3: resolveReviewThread(input: {threadId: "PRRT_zzz"}) { thread { id isResolved } }
}'
```

**Benefits**:

- 1 API call instead of N calls
- Reduced network latency (1 round trip vs N)
- Atomic operation (all succeed or all fail)

## Related Memories

When reviewing PRs, consult these Serena memories for context:

| Memory | Purpose |
|--------|---------|
| `pr-review-007-merge-state-verification` | GraphQL source of truth for merge state |
| `pr-review-004-thread-resolution-single` | Single thread resolution via GraphQL |
| `pr-review-005-thread-resolution-batch` | Batch thread resolution efficiency |
| `pr-review-008-session-state-continuity` | Session context for multi-round reviews |
| `ai-quality-gate-failure-categorization` | Infrastructure vs code quality failures |
| `session-log-fixer` (skill) | Diagnose and fix session protocol failures |
