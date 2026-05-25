---
name: git-advanced-workflows
version: 1.1.0
model: claude-sonnet-4-6
description: Advanced Git workflows including rebasing, cherry-picking, bisect, worktrees, and reflog. Use when managing complex Git histories, collaborating on feature branches, or recovering from repository issues.
license: MIT
---

# Git Advanced Workflows

Advanced Git techniques for clean history, effective collaboration, and confident recovery.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `rebase my branch` | Interactive or standard rebase guidance |
| `cherry-pick a commit` | Cherry-pick with conflict resolution |
| `find the breaking commit` | Git bisect workflow |
| `recover lost commits` | Reflog exploration and recovery |
| `use git worktrees` | Worktree setup and management |

## Process

### Phase 1: Assess the Situation

1. Identify which workflow applies (rebase, cherry-pick, bisect, worktree, recovery)
2. Check current branch state: `git status`, `git log --oneline -10`
3. Create a safety branch before any destructive operation: `git branch backup-<timestamp>`
   - macOS/Linux (bash/zsh): `git branch backup-$(date +%s)`
   - Windows PowerShell: `git branch backup-$(Get-Date -UFormat %s)`

### Phase 2: Execute the Workflow

#### Rebase: Clean Up Feature Branch Before PR

```bash
git checkout feature/user-auth
git rebase -i main
# Squash "fix typo" commits, reword messages, reorder logically
git push --force-with-lease origin feature/user-auth
```

**Rebase operations:** `pick` (keep), `reword` (change message), `edit` (amend content), `squash` (combine keeping message), `fixup` (combine discarding message), `drop` (remove).

**Autosquash pattern:**

```bash
git commit --fixup HEAD        # Mark as fixup for previous commit
git rebase -i --autosquash main  # Auto-marks fixup commits
```

**Split a commit:**

```bash
git rebase -i HEAD~3          # Mark commit with 'edit'
git reset HEAD^               # Reset commit, keep changes in working tree (unstaged)
git add file1.py && git commit -m "feat: add validation"
git add file2.py && git commit -m "feat: add error handling"
git rebase --continue
```

#### Cherry-Pick: Apply Hotfix to Multiple Releases

```bash
git checkout main
git commit -m "fix: critical security patch"

git checkout release/2.0
git cherry-pick abc123

git checkout release/1.9
git cherry-pick abc123
# On conflict: fix files, git add, git cherry-pick --continue
```

**Partial cherry-pick** (specific files only):

```bash
git show --name-only abc123
git restore --source=abc123 -- path/to/file1.py path/to/file2.py
git commit -m "cherry-pick: apply specific changes from abc123"
```

#### Bisect: Find Bug Introduction

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.1.0
# Git checks out middle commit. Run tests, mark good/bad, repeat.
git bisect reset  # When done
```

**Automated bisect:**

```bash
git bisect start HEAD v2.1.0
git bisect run ./test.sh
# test.sh: exit 0 = good, 125 = skip, any other non-zero = bad
```

#### Worktree: Multi-Branch Development

```bash
git worktree add ~/worktrees/myapp-hotfix hotfix/critical-bug
# Work in the new worktree using the -C flag to avoid changing the current directory.
# e.g., git -C ~/worktrees/myapp-hotfix commit -a -m "fix: critical bug"
git worktree remove ~/worktrees/myapp-hotfix  # Clean up when done
git worktree prune  # Remove stale entries
```

#### Recovery: Undo Mistakes with Reflog

```bash
git reflog                     # Find lost commit hash
git reset --hard def456        # Restore to that state
# Or create branch: git branch recovery def456
```

**Abort operations in progress:**

```bash
git rebase --abort
git merge --abort
git cherry-pick --abort
git bisect reset
```

**Other recovery commands:**

```bash
git restore --source=abc123 path/to/file  # Restore file from commit
git reset --soft HEAD^                     # Undo commit, keep changes staged
git reflog                                 # 1. Find the hash of the desired commit
git branch recovered abc123                # 2. Create a branch from that hash (within reflog retention; ~90 days by default, configurable)
```

### Phase 3: Verify and Clean Up

1. Confirm working tree is clean: `git status`
2. Validate history: `git log --oneline` matches expectations
3. Run tests after any history rewrite
4. Remove worktrees if created: `git worktree list`

## Decision Guide

### Rebase vs Merge

| Use Rebase | Use Merge |
|------------|-----------|
| Cleaning local commits before push | Integrating completed features into main |
| Keeping feature branch current with main | Preserving exact collaboration history |
| Creating linear history for review | Public branches used by others |

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Rebasing shared branches | Rewrites history for all collaborators | Merge for shared branches |
| `--force` without `--force-with-lease` | Overwrites teammates' work | Always `--force-with-lease` |
| Bisecting on dirty working tree | Checkout fails with uncommitted changes | Commit or stash first |
| Orphaned worktrees | Consume disk space silently | Remove after use |
| No backup before complex rebase | No recovery path if rebase fails | Create safety branch first |

## Verification

- [ ] Working tree is clean (`git status`)
- [ ] Branch history matches expectations (`git log --oneline`)
- [ ] Tests pass after history rewrite
- [ ] Force push used `--force-with-lease`
- [ ] Worktrees cleaned up (`git worktree list`)
