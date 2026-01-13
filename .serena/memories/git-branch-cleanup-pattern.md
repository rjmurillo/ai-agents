# Skill-Git-005: Branch Cleanup Pattern

**Statement**: Delete local branch before checkout when branch exists from previous operations

**Context**: Before checking out PR branches in autonomous loops or multi-cycle sessions where branches may persist from previous cycles. Applies to any workflow that repeatedly checks out the same branch names.

**Evidence**: 2025-12-24 PR monitoring: 4 `fatal: a branch named 'X' already exists` errors when checking out PR branches. Pattern: loop creates branches in Cycle N, Cycle N+1 checkout fails. Cleanup before checkout eliminates all errors. Lines 168-172 of retrospective.

**Atomicity**: 90% | **Impact**: 7/10

## Pattern

Unconditional branch cleanup before checkout:

### Single Branch Cleanup

```bash
# Delete local branch (ignore if doesn't exist)
git branch -D "<branch-name>" 2>/dev/null || true

# Then checkout fresh from remote
git checkout -b "<branch-name>" "origin/<branch-name>"
```

### Combined Pattern (fetch + cleanup + checkout)

```bash
# Full pattern for reliable checkout
git fetch origin
git branch -D "<branch-name>" 2>/dev/null || true
git checkout -b "<branch-name>" "origin/<branch-name>"
```

### Batch Cleanup for Multiple PRs

```bash
for pr in 300 299 285; do
  branch=$(gh pr view "$pr" --json headRefName -q .headRefName)
  git branch -D "$branch" 2>/dev/null || true
  git checkout -b "$branch" "origin/$branch"
  # Work on branch...
done
```

## Anti-Pattern

Conditional cleanup (check if branch exists first):

```bash
# AVOID: Checking existence adds complexity
if git show-ref --verify --quiet "refs/heads/$branch"; then
  git branch -D "$branch"
fi
git checkout -b "$branch" "origin/$branch"

# USE INSTEAD: Unconditional cleanup
git branch -D "$branch" 2>/dev/null || true
git checkout -b "$branch" "origin/$branch"
```

**Why**: The `-D` flag with stderr redirect and `|| true` handles both cases (exists/doesn't exist) in one line. Simpler and more reliable.

**Flags Explained**:

- `-D`: Force delete (combines `-d -f`)
- `2>/dev/null`: Suppress error if branch doesn't exist
- `|| true`: Ensure command succeeds even if branch doesn't exist (prevents pipeline failure)

**Evidence**: 0 branch errors after implementing pattern, 4 errors before.

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
