---
description: Commit, push, and open a PR
allowed-tools: Bash(git checkout -b:*), Bash(git switch -c:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(git diff:*), Bash(git branch:*), Bash(mkdir:-p .agents/scratch)
# Security note: no bare Write grant. This command reads untrusted repository
# diffs and already holds git add, commit and push, so a pre-approved
# unrestricted Write would let a prompt-injected diff redirect the body write
# to a source or hook file and publish it. The host prompts for the single
# .agents/scratch body write instead. Issue #4825.
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
4. Create `.agents/scratch`, then write a new file there adapting the template
   to describe THIS branch's changes (e.g. `.agents/scratch/PR-123-BODY.md`):
   - **Fill in** all sections with actual change information from git diff
   - **Replace** placeholder comments with substantive content
   - **Check** appropriate Type of Change boxes based on actual changes
   - **List** specific files changed, test coverage added, security impacts
   - **Do NOT** leave template comments like `<!-- Brief description -->` unfilled
   - **Do NOT** copy the template verbatim - adapt every section to your changes
   - **Include** an `## Acceptance criteria` heading with `- [ ]` or `* [ ]` bullets. The Validate Spec Coverage job reads these from the PR body, not the linked issue. Any unchecked box makes the signal report FAIL, and that FAIL does not block the merge, so check a box only once the criterion is actually met. Numbered criteria are not recognized.
5. Create a pull request using the new_pr skill script:

   <!-- vendor-portability: declared. This command reads the consumer's
   `.github/PULL_REQUEST_TEMPLATE.md` and writes the consumer's
   `.agents/scratch/` body file. It resolves the helper from the installed
   Copilot or Claude plugin root. The `.claude` fallback is only for this
   repository's self-hosted source checkout; `scripts/pr/` is inside the
   shipped github skill, not the upstream-only top-level scripts/ tree.
   Issue #4764. -->

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --title "<conventional commit title>" --body-file .agents/scratch/PR-123-BODY.md
   ```

   - Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
   - Body SHOULD include GitHub issue linking keywords to auto-close issues:
     - `Closes #123`: auto-closes issue when PR merges
     - `Fixes #456`: auto-fixes issue when PR merges
     - `Resolves #789`: auto-resolves issue when PR merges
   - Ensure PR template sections are completed

You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.
