# Retrospective: PR Co-Mingling Root Cause Analysis

**Date**: 2025-12-31
**Session**: 105/108 (PR Queue Merge Management)
**Severity**: High - Required extensive remediation

## Executive Summary

Multiple PRs (#562, #563, #564, #565) had their changes co-mingled due to commits being made while the wrong branch was checked out. This resulted in:
- Cherry-pick conflicts during merge attempts
- Merge queue blockages
- Manual branch recreation required
- ~3 hours of remediation work

## Root Cause: Trust-Based Compliance for Git Operations

### The Failure

Commits were pushed to branches without verifying the current checked-out branch first. The agent workflow relied on **assumed** branch state rather than **verified** branch state.

### Specific Failure Pattern

```bash
# What happened (WRONG)
git add .
git commit -m "feat: add feature X"  # Assumed we were on branch-X
git push origin branch-X             # Pushed to wrong branch

# What should have happened (CORRECT)
git branch --show-current            # VERIFY first
# Output: branch-Y                   # Oops, wrong branch!
git checkout branch-X                # Switch to correct branch
git add .
git commit -m "feat: add feature X"
git push origin branch-X
```

### Contributing Factors

1. **Parallel worktree confusion**: Multiple worktrees existed for different PRs
2. **Context switches**: Moving between PRs without explicit branch verification
3. **Trust over verification**: Assumed branch state was correct
4. **Missing pre-commit hook**: No gate to verify branch before commit

## Evidence

### Affected PRs

| PR | Expected Branch | Issue |
|----|-----------------|-------|
| #562 | feat/163-job-retry | Mixed commits from #563, #564, #565 |
| #563 | feat/163-merge-conflict | Commits from other PRs |
| #564 | feat/163-job-retry | Verdict regex from #563 |
| #565 | feat/97-thread-management | Clean after recreation |

### Remediation Actions

1. **PR #562**: Cherry-picked only relevant commits, force pushed
2. **PR #563**: Rebased to create clean branch
3. **PR #564**: Rebased to create clean branch
4. **PR #565**: Recreated entirely from main, cherry-picked unique files

## Lessons Learned

### L1: Branch Verification is Non-Negotiable

**Memory**: `git-003-staged-changes-guard`, `git-004-branch-switch-file-verification`

Before ANY mutating git operation (commit, push, reset), MUST run:

```bash
git branch --show-current
```

### L2: Worktree Isolation Protocol

When using worktrees for parallel PR work:

```bash
# Step 1: Navigate to worktree
cd /path/to/worktree-pr-XXX

# Step 2: Verify you're in the right worktree
git branch --show-current
# Expected: feat/XXX-description

# Step 3: Only then proceed with changes
```

### L3: Commit Atomicity by Branch

Each branch should contain ONLY commits related to its PR scope:
- If a commit touches files unrelated to the PR, STOP
- Verify branch context before proceeding
- Never batch commits across multiple PRs in one branch

## Preventive Measures

### Immediate (Session 108+)

1. **Explicit branch check**: Add to all commit workflows
2. **Session log branch tracking**: Document current branch in session logs
3. **Worktree naming convention**: Use `worktree-pr-{number}` consistently

### Future (Consider for implementation)

1. **Pre-commit hook**: Validate branch name matches expected pattern
2. **Claude Code hook**: Intercept git commands and verify branch
3. **PR-branch mapping**: Maintain explicit mapping of PR numbers to branches

## Impact Assessment

| Metric | Value |
|--------|-------|
| PRs affected | 4 |
| Hours to remediate | ~3 |
| Merge queue delays | ~12 hours |
| Commits requiring cherry-pick | ~15 |

## Process Changes Required

Update `.agents/governance/PROJECT-CONSTRAINTS.md`:

```markdown
### Branch Operation Verification (MUST)

Before ANY mutating git or GitHub operation, you MUST verify the current branch:

git branch --show-current
```

## Related Memories

- `git-003-staged-changes-guard`
- `git-004-branch-switch-file-verification`
- `coordination-001-branch-isolation-gate`
- `parallel-001-worktree-isolation`

## Sign-off

- **Analysis by**: Claude Opus 4.5
- **Session**: 105/108
- **Status**: Root cause identified, preventive measures documented
