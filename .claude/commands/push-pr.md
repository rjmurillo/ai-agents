---
description: Commit, push, and open a PR
allowed-tools:
  - Bash(git checkout -b:*)
  - Bash(git switch -c:*)
  - Bash(git add:*)
  - Bash(git status:*)
  - Bash(git push:*)
  - Bash(git commit:*)
  - Bash(pwsh .claude/skills/github/scripts/pr/New-PR.ps1:*)
  - Bash(git diff:*)
  - Bash(git branch:*)
# Security Note: Wildcards are Claude Code tool patterns, not shell globs.
# The Bash tool executor must sanitize arguments to prevent command injection (CWE-78).
# Shell metacharacters (; && | $() etc.) should be escaped/rejected before execution.
---

# Push PR Command

## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`

## Your task

Based on the above changes:

1. Create a new branch if on main
   1. Determine the type of change that maps to conventional commit type followed by a 3-5 word description (e.g., fix/parser-log-enrichment)
2. Push the branch to origin
3. Create a pull request using the New-PR skill script:

   ```bash
   pwsh .claude/skills/github/scripts/pr/New-PR.ps1 -Title "<conventional commit title>" -BodyFile .github/PULL_REQUEST_TEMPLATE.md
   ```

   - Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
4. You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.
