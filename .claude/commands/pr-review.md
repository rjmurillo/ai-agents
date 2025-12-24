---
allowed-tools: Bash(git:*), Bash(gh:*), Bash(pwsh:*), Task, Skill, Read, Write, Edit, Glob, Grep
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup]
description: Respond to PR review comments for the specified pull request(s)
---

# PR Review Command

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
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

Verify: PR exists, is open (state != MERGED, CLOSED), targets current repo.

**CRITICAL - Verify PR Merge State (Skill-PR-Review-006)**:

Before proceeding with review work, verify PR has not been merged via GraphQL (source of truth):

```powershell
# Check merge state via Test-PRMerged.ps1
pwsh .claude/skills/github/scripts/pr/Test-PRMerged.ps1 -PullRequest {number}
$merged = $LASTEXITCODE -eq 1

if ($merged) {
    Write-Host "PR #{number} is already merged. Skipping review work." -ForegroundColor Yellow
    continue  # Skip to next PR
}
```

**Why this matters**: `gh pr view --json state` may return stale "OPEN" for recently merged PRs, leading to wasted effort (see Issue #321, Session 85).

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
| All comments resolved | Each comment has [COMPLETE] or [WONTFIX] status | Yes |
| No new comments | Re-check after 45s wait returned 0 new | Yes |
| CI checks pass | `gh pr checks` all green (including AI Quality Gate) | Yes |
| No unresolved threads | GraphQL query for unresolved reviewThreads (see Thread Resolution Protocol) | Yes |
| PR not merged | Test-PRMerged.ps1 exit code 0 | Yes |
| Commits pushed | `git status` shows "up to date with origin" | Yes |

**If ANY criterion fails**: Do NOT claim completion. The agent must loop back to address the issue.

### Verification Command

```bash
# Run after each PR to verify completion
for pr in pr_numbers; do
  echo "=== PR #$pr Completion Check ==="
  gh pr checks $pr --json name,state | jq '[.[] | select(.state != "SUCCESS")]'
  # Note: reviewThreads requires GraphQL, not gh pr view --json
  gh api graphql -f query="query { repository(owner: \"OWNER\", name: \"REPO\") { pullRequest(number: $pr) { reviewThreads(first: 50) { nodes { isResolved } } } } }" | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)]'
done
```

## Thread Resolution Protocol

### Overview (Skills PR-Review-004, PR-Review-005)

**CRITICAL**: Replying to a review comment does NOT automatically resolve the thread. Thread resolution requires a separate GraphQL mutation.

### Single Thread Resolution (Skill-PR-Review-004)

After replying to a review comment, resolve the thread via GraphQL:

```bash
# Step 1: Reply to comment (handled by pr-comment-responder skill)
# Step 2: Resolve thread (REQUIRED separate step)
gh api graphql -f query='
mutation {
  resolveReviewThread(input: {threadId: "PRRT_xxx"}) {
    thread { isResolved }
  }
}' -f threadId="PRRT_xxx"
```

**Why this matters**: pr-comment-responder skill replies to comments, but threads remain unresolved unless explicitly resolved via GraphQL. Unresolved threads block PR merge per branch protection rules.

### Batch Thread Resolution (Skill-PR-Review-005)

For 2+ threads, use GraphQL mutation aliases for efficiency:

```bash
gh api graphql -f query='
mutation {
  t1: resolveReviewThread(input: {threadId: "PRRT_xxx"}) { thread { id isResolved } }
  t2: resolveReviewThread(input: {threadId: "PRRT_yyy"}) { thread { id isResolved } }
  t3: resolveReviewThread(input: {threadId: "PRRT_zzz"}) { thread { id isResolved } }
  t4: resolveReviewThread(input: {threadId: "PRRT_aaa"}) { thread { id isResolved } }
  t5: resolveReviewThread(input: {threadId: "PRRT_bbb"}) { thread { id isResolved } }
}
'
```

**Benefits**:
- 1 API call instead of N calls (e.g., 1 call for 5 threads vs 5 calls)
- Reduced network latency (1 round trip vs N)
- Atomic operation (all succeed or all fail)

**When to use**: 2+ threads to resolve (break-even point)

### Verification

```bash
# Check for unresolved threads
unresolved_count=$(gh api graphql -f query='
query {
  repository(owner: "OWNER", name: "REPO") {
    pullRequest(number: PR_NUMBER) {
      reviewThreads(first: 100) {
        nodes { id isResolved }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length')

echo "Unresolved threads: $unresolved_count"
# Should be 0 before claiming completion
```

**Reference**: Session 85 discovered this requirement when PR #315 had 18 unresolved threads despite all comments being replied to.

## Examples

```bash
/pr-review 194                              # Single PR
/pr-review 53,141,143                       # Multiple PRs sequentially
/pr-review 53,141,143 --parallel            # Multiple PRs in parallel
/pr-review all-open --parallel              # All open PRs needing review
/pr-review 194 --parallel --cleanup=false   # Skip cleanup
```
