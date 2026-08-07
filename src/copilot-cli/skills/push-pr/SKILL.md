---
name: push-pr
description: Commit, push, and open a PR
allowed-tools: Bash(git checkout -b:*), Bash(git switch -c:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(python3:*/pr/new_pr.py*), Bash(git diff:*), Bash(git branch:*), Bash(mkdir:-p .agents/scratch), Write
user-invocable: true
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
4. Create `.agents/scratch`, choose a unique per-run PR body filename, then use
   the Write tool to write the adapted template:

   ```bash
   mkdir -p .agents/scratch
   BODY_FILE=".agents/scratch/pr-body-<unique-uuid>.md"
   ```

   - Replace `<unique-uuid>` with a new UUID before writing the file
   - **Fill in** all sections with actual change information from git diff
   - **Replace** placeholder comments with substantive content
   - **Check** appropriate Type of Change boxes based on actual changes
   - **List** specific files changed, test coverage added, security impacts
   - **Do NOT** leave template comments like `<!-- Brief description -->` unfilled
   - **Do NOT** copy the template verbatim - adapt every section to your changes
   - **Include** an `## Acceptance criteria` heading with `- [ ]` or `* [ ]` bullets. The Validate Spec Coverage job reads these from the PR body, not the linked issue. Any unchecked box makes the signal report FAIL, and that FAIL does not block the merge, so check a box only once the criterion is actually met. Numbered criteria are not recognized.
5. Create a pull request using the new_pr skill script:

   ```bash
   SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"
   python3 "$SCRIPTS_DIR/pr/new_pr.py" --title "<conventional commit title>" --body-file "$BODY_FILE"
   ```

- Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
- Body SHOULD include GitHub issue linking keywords to auto-close issues:
  - `Closes #123`: auto-closes issue when PR merges
  - `Fixes #456`: auto-fixes issue when PR merges
  - `Resolves #789`: auto-resolves issue when PR merges
- Ensure PR template sections are completed

You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.

<!-- vendor-portability: .agents/scratch is created in the consumer workspace
for one-run PR body files. It is not an upstream repository dependency. -->
