# Skill: Verify File State After Branch Switches

## Problem

In Session 100, when switching from `feat/282-centralize-bot-authors` to `main` and then creating `feat/275-unified-rate-limit`, edits to `GitHubHelpers.psm1` were lost because the file reverted to main's version.

## Root Cause

Branch switches reset working directory to the target branch state. Uncommitted or staged changes on the previous branch are lost if not committed first.

## Verification Pattern

After any `git checkout` or branch switch:

```bash
# 1. Verify current branch
git branch --show-current

# 2. Check if expected file exists and has expected content
git diff HEAD~1 --name-only  # See what changed in last commit

# 3. If working on a file that should have edits, verify:
head -20 {file_path}  # Quick visual check
```

## Safe Branch Switch Workflow

```bash
# Before switching branches
git status  # Check for uncommitted changes
git stash   # If needed, stash changes

# Switch branch
git checkout {new-branch}

# After switching
git stash pop  # If you stashed
# OR re-apply edits if they belong on the new branch
```

## Anti-Pattern

```text
BAD:  git checkout main && git checkout -b new-branch  # Assumes file state preserved
GOOD: git status && git checkout main && git checkout -b new-branch && verify file state
```

## Source

- Session 100 (2025-12-29)
- Lost ~50 lines of edits to GitHubHelpers.psm1
