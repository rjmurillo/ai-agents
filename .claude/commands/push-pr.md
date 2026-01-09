---
description: Commit, push, and open a PR
allowed-tools: [Bash(git checkout --branch:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*), Bash(git diff:*), Bash(git branch:*)]
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
3. Create a pull request using `gh pr create` based on the changes in this branch
   - Title is conventional commit, and body uses @.github/PULL_REQUEST_TEMPLATE.md
4. You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.
