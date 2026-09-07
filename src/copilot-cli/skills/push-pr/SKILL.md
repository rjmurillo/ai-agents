---
name: push-pr
version: 1.0.0
description: Commit the working tree, push the branch, and open a pull request with the repository template filled in from the real diff. Use when you say `push and open a PR`, `open a pull request`, or `push this branch`. Do NOT use to run the pre-ship review gates (use ship), and do NOT use to validate PR metadata alone (use validate-pr-description).
license: MIT
allowed-tools: Bash(git checkout -b:*), Bash(git switch -c:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(python3:-I */pr/new_pr.py*), Bash(git diff:*), Bash(git branch:*), Bash(mkdir:-p .agents/scratch), Edit(.agents/scratch/pr-body-*.md)
# Security note: python3 -I is the identity-hardened form (issue #4825).
# The Edit entry above is scoped to the secure allocator's output file only.
# The Bash tool executor must sanitize arguments to prevent command injection (CWE-78).
# Shell metacharacters (; && | etc.) should be escaped/rejected before execution.
user-invocable: true
---

# Push PR

Commit, push, and open a pull request whose body is adapted from the real diff
rather than copied from the template.

Migrated from `.claude/commands/push-pr.md` under ADR-064, which makes skills the
single user-invocable surface. The scoped `allowed-tools` grant, the
identity-hardened `python3 -I` form, and both vendor-portability declarations
carry over unchanged: they are the security contract, not formatting.

## Triggers

`push and open a PR`, `open a pull request`, `push this branch`,
`commit and push`

## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`

## Process

Based on the above changes:

1. Create a new branch if on main.
   1. Determine the type of change that maps to a conventional commit type
      followed by a 3-5 word description (for example, `fix/parser-log-enrichment`).
2. Push the branch to origin.
3. Read @.github/PULL_REQUEST_TEMPLATE.md
4. Run the secure path allocator:

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --prepare-body-file
   ```

   - Copy the returned path exactly. Do not store it in a shell variable because
     each tool call runs in a fresh shell.
   - Use the Edit tool to replace `<!-- replace with PR body -->` in that exact
     file with the adapted template.
   - **Fill in** all sections with actual change information from git diff
   - **Replace** placeholder comments with substantive content
   - **Check** appropriate Type of Change boxes based on actual changes
   - **List** specific files changed, test coverage added, security impacts
   - **Do NOT** leave template comments like `<!-- Brief description -->` unfilled
   - **Do NOT** copy the template verbatim - adapt every section to your changes
   - **Include** an `## Acceptance criteria` heading with `- [ ]` or `* [ ]` bullets. The Validate Spec Coverage job reads these from the PR body, not the linked issue. Any unchecked box makes the signal report FAIL, and that FAIL does not block the merge, so check a box only once the criterion is actually met. Numbered criteria are not recognized.
5. Create a pull request using the new_pr skill script:

   <!-- vendor-portability: declared. This skill reads the consumer's
   `.github/PULL_REQUEST_TEMPLATE.md` and writes the consumer's
   `.agents/scratch/` body file. It resolves the helper from the installed
   Copilot or Claude plugin root. The `.claude` fallback is only for this
   repository's self-hosted source checkout; `scripts/pr/` is inside the
   shipped github skill, not the upstream-only top-level scripts/ tree.
   Issue #4764. -->

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --title "<conventional commit title>" --body-file ".agents/scratch/pr-body-<returned-uuid>.md"
   ```

- Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
- Body SHOULD include GitHub issue linking keywords to auto-close issues:
  - `Closes #123`: auto-closes issue when PR merges
  - `Fixes #456`: auto-fixes issue when PR merges
  - `Resolves #789`: auto-resolves issue when PR merges
- Ensure PR template sections are completed

You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.

## Verification

- [ ] Branch created off main when the working branch was main, never a push to main
- [ ] Title follows conventional commit format
- [ ] Body written into the allocator's returned path, copied exactly, never through a shell variable
- [ ] Every template section adapted from the real diff, with no placeholder comment left in
- [ ] An `## Acceptance criteria` heading present with `- [ ]` bullets, checked only where met
- [ ] Issue-linking keyword present, and a closing keyword used only when the diff delivers what the issue asks

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Storing the allocator path in a shell variable | Each tool call runs a fresh shell, so the variable is empty on the next call and the body lands nowhere | Copy the returned path literally into the next call |
| Copying the template verbatim | Ships placeholder comments as the PR description, and the spec-coverage job reads them | Adapt every section from the diff |
| Numbered acceptance criteria | The Validate Spec Coverage job reads `- [ ]` and `* [ ]` only, so numbered items are invisible to it | Use checkbox bullets |
| Checking a criterion box before it is met | The signal reports a pass the PR does not have, and the FAIL it should have shown does not block merge | Check a box only once the criterion holds |
| Widening the `allowed-tools` grant to bare `Bash` | Removes the CWE-78 argument scoping that makes this skill safe to auto-approve | Add a specific scoped entry |

## Extension Points

- **Other forges.** Steps 4 and 5 call `new_pr.py`. A non-GitHub forge swaps that
  helper; the template-adaptation rules in step 4 are forge-independent.
- **Template changes.** Step 4's section list follows the repository PR
  template read in step 3. When that template gains a parsed section, add it to
  step 4 and to the Verification list together.
- **Branch naming.** Step 1's conventional-type mapping is the repository
  convention; a project with a different scheme changes that sub-step alone.

<!-- vendor-portability: .agents/scratch is created in the consumer workspace
for one-run PR body files. It is not an upstream repository dependency. -->
