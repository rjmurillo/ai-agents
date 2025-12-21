# Batch PR Review Command

Process multiple PR review comments in parallel using git worktrees for isolation.

## Usage

```
/batch-pr-review <PR_NUMBERS>
```

**Examples:**
- `/batch-pr-review 53,141,143` - Process PRs #53, #141, #143
- `/batch-pr-review 194` - Process single PR #194
- `/batch-pr-review all-open` - Process all open PRs with review comments

## Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `PR_NUMBERS` | Comma-separated PR numbers, or `all-open` for all open PRs | Yes |

## Workflow

### Phase 1: Setup

1. Parse PR numbers from input
2. For `all-open`: Query open PRs with unresolved review comments
3. Validate each PR exists and is open
4. Create worktree root directory at `../worktree-pr-{number}` for each PR

### Phase 2: Parallel Execution

For each PR, launch a background agent using:

```python
Task(
    subagent_type="pr-comment-responder",
    prompt="Process PR #{number}",
    run_in_background=True
)
```

The pr-comment-responder agent will:
1. Checkout the PR's branch in its dedicated worktree
2. Fetch all review comments
3. Add eyes reactions to acknowledge comments
4. Analyze and triage each comment
5. Implement fixes for actionable items
6. Reply to threads with resolution details
7. Commit and push changes

### Phase 3: Monitoring

Poll background agents until all complete:

```python
TaskOutput(task_id="{agent_id}", block=True, timeout=300000)
```

Display progress table:

| PR | Branch | Status | Comments | Fixed | Pushed |
|----|--------|--------|----------|-------|--------|

### Phase 4: Cleanup

For each worktree:

1. Check for uncommitted changes (`git status --short`)
2. If changes exist:
   - Stage all changes (`git add .`)
   - Commit with message: `chore(pr-{number}): finalize review response`
   - Push to remote
3. Verify worktree is clean
4. Remove worktree (`git worktree remove`)

### Phase 5: Summary

Output consolidated summary:

```markdown
## Batch PR Review Complete

| PR | Branch | Comments | Resolved | Commit | Status |
|----|--------|----------|----------|--------|--------|
| #53 | feat/xyz | 4 | 4 | abc1234 | COMPLETE |
| #141 | fix/abc | 2 | 2 | def5678 | COMPLETE |

**Total**: X PRs processed, Y comments resolved, Z commits pushed
```

## Worktree Structure

```
D:\src\GitHub\rjmurillo-bot\
├── ai-agents/                    # Main repository (current)
├── worktree-pr-53/               # PR #53 worktree
│   └── (full repo checkout on feat/xyz branch)
├── worktree-pr-141/              # PR #141 worktree
│   └── (full repo checkout on fix/abc branch)
└── ...
```

## Error Handling

| Error | Recovery |
|-------|----------|
| PR not found | Skip with warning, continue others |
| Branch checkout fails | Report error, skip PR |
| Agent timeout (5 min) | Report partial status, continue cleanup |
| Push fails | Retry once, then report for manual intervention |
| Worktree removal fails | Force removal with `--force` flag |

## Prerequisites

- `gh` CLI authenticated
- Git configured with push access
- PowerShell available for GitHub skill scripts

## Related

- `/pr-comment-responder` - Single PR review command
- `.claude/skills/github/` - GitHub PowerShell scripts
- `.agents/SESSION-PROTOCOL.md` - Session protocol requirements
