# Skill: Lost Code Investigation Workflow

## When to Use

When code is reported missing, a function "doesn't exist", or an issue references code that can't be found on main.

## Investigation Checklist

### Step 1: Search All Git History

```bash
# Search for the term across ALL branches (including unmerged)
git log --all -S "{function_name}" --oneline --source

# If found, shows which branch contains it
# Example output:
# f12f237 refs/remotes/origin/feat/pr-162-phase4 feat: Add detection script
```

### Step 2: Check Related PRs

```bash
# Search closed PRs
gh pr list --state closed --search "{keyword}" --json number,title,state,mergedAt

# Look for mergedAt: null (closed without merge)
```

### Step 3: Check Orphaned Branches

```bash
# List all remote branches
git branch -a | grep -i "{keyword}"

# Check if branch still exists
git ls-tree -r remotes/origin/{branch} --name-only | grep -i "{file}"
```

### Step 4: Extract and Recover

```bash
# View file from unmerged branch
git show remotes/origin/{branch}:{path/to/file}

# Save to current branch
git show remotes/origin/{branch}:{path/to/file} > recovered_file.ps1
```

### Step 5: Investigate Why Not Merged

```bash
# Get PR details
gh pr view {number} --json title,state,closedAt,body,comments

# Check last comments for closure reason
```

## Common Causes of "Lost" Code

| Cause | Detection | Recovery |
|-------|-----------|----------|
| PR closed without merge | `mergedAt: null` | Recover from branch |
| Incorrect triage bot closure | "superseded" in comments | Reopen or new PR |
| Branch deleted after close | No remote branch | Check local or reflog |
| Bad merge conflict resolution | `git log --all -S` finds it | Cherry-pick |

## Key Principle

**Never trust "doesn't exist" without searching git history.** Code can exist on:
- Unmerged branches
- Closed PRs
- Orphaned commits
- Stale remote branches

A quick `git log --all -S` search takes seconds and prevents false stale closures.

## Source

- Session 100 (2025-12-29)
- Issues #238, #293 recovered from unmerged branches
- PRs #202, #203 incorrectly closed by triage bot
