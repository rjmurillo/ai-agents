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
3. Read @.github/PULL_REQUEST_TEMPLATE.md
4. Write a new file adapting the template to describe THIS branch's changes (e.g. /tmp/PR-123-BODY.md):
   - **Fill in** all sections with actual change information from git diff
   - **Replace** placeholder comments with substantive content
   - **Check** appropriate Type of Change boxes based on actual changes
   - **List** specific files changed, test coverage added, security impacts
   - **Do NOT** leave template comments like `<!-- Brief description -->` unfilled
   - **Do NOT** copy the template verbatim - adapt every section to your changes
5. Create a pull request using the New-PR skill script:

   ```bash
   pwsh .claude/skills/github/scripts/pr/New-PR.ps1 -Title "<conventional commit title>" -BodyFile /tmp/PR-123-BODY.md
   ```

   - Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)

You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.
