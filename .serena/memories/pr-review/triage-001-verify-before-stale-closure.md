# Skill: Verify Git History Before Closing Issues as Stale

## Problem

In Session 100, issues #238 and #293 were incorrectly closed as "stale" because the referenced functions (`Get-CopilotAnnouncement`, `Detect-CopilotFollowUpPR`) didn't exist on `main`. However, the code existed on unmerged branches (`feat/pr-162-phase4`, `copilot/add-copilot-context-synthesis`) from PRs #202/#203 that were incorrectly closed by triage bot.

## Root Cause

The triage bot closed PRs #202/#203 claiming content was "superseded" because template documentation existed. But the actual **PowerShell implementation** (268 lines) was never merged.

## Mandatory Checklist Before Closing as Stale

```bash
# 1. Search ALL git history (including unmerged branches)
git log --all -S "{function_name}" --oneline

# 2. Check for related PRs (open AND closed)
gh pr list --state all --search "{function_name}"

# 3. Check for orphaned branches
git branch -a | grep -i "{keyword}"

# 4. If found on unmerged branch, investigate WHY it wasn't merged
git show {branch}:{file_path} | head -50
```

## Anti-Pattern

```text
BAD:  "Function doesn't exist on main" → Close as stale
GOOD: "Function doesn't exist on main" → Search git history → Found on unmerged branch → Recover
```

## Recovery Command

```bash
# Extract file from unmerged branch
git show remotes/origin/{branch}:{path/to/file} > recovered_file.ps1
```

## Source

- Session 100 (2025-12-29)
- Issues #238, #293 (incorrectly closed, then reopened)
- PRs #202, #203 (incorrectly closed by triage bot)
- Recovery PR #493

## Related

- [triage-002-bot-closure-verification](triage-002-bot-closure-verification.md)
