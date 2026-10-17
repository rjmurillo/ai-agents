---
name: push-pr
version: 1.0.0
description: Commit the working tree, push the branch, and open a pull request with the repository template filled in from the real diff. Use when you say `push and open a PR`, `open a pull request`, or `push this branch`. Do NOT use to run the pre-ship review gates (use ship), and do NOT use to validate PR metadata alone (use validate-pr-description).
license: MIT
allowed-tools: Bash(git checkout -b:*), Bash(git switch -c:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(python3:-I */pr/new_pr.py*), Bash(uv run --frozen python -I scripts/validation/pr_description.py*), Bash(git diff:*), Bash(git branch:*), Bash(mkdir:-p .project-toolkit/scratch), Edit(.project-toolkit/scratch/pr-body-*.md)
# Security note: python3 -I is the identity-hardened form (issue #4825).
# The Edit entry above is scoped to the secure allocator's output file only.
# The Bash tool executor must sanitize arguments to prevent command injection (CWE-78).
# Shell metacharacters (; && | etc.) should be escaped/rejected before execution.
user-invocable: true
metadata:
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan routes push-only requests to push-pr
    user-facing: true
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
2. Read @.github/PULL_REQUEST_TEMPLATE.md. Step 3 seeds it into the body file; use this copy only when the seeded file holds the marker alone.
3. Run the secure path allocator:

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --prepare-body-file
   ```

   - On Windows the allocator refuses to run. Follow the
     Windows PR Body Fallback section below for steps 3, 4, 5, and 7.
   - Copy the returned path exactly. Do not store it in a shell variable because
     each tool call runs in a fresh shell.
   - The file starts with the line `<!-- replace with PR body -->`, followed by the
     repository PR template. Use the Edit tool to fill the template sections in
     that exact file, then delete the marker line. A body that still contains the
     marker text anywhere is rejected.
   - If the file holds only the marker, the repository has no usable template.
     Replace it with the template you read in step 2, adapted to the change.
   - **Fill in** all sections with actual change information from git diff
   - **Replace** placeholder comments with substantive content
   - **Check** appropriate Type of Change boxes based on actual changes
   - **List** specific files changed, test coverage added, security impacts
   - **Do NOT** leave template comments like `<!-- Brief description -->` unfilled
   - **Do NOT** copy the template verbatim - adapt every section to your changes
   - **Include** an `## Acceptance criteria` heading with `- [ ]` or `* [ ]` bullets. The Validate Spec Coverage job reads these from the PR body, not the linked issue. When the PR links a spec or an issue, an unchecked box or a missing section makes the deterministic check report FAIL, and that FAIL does not block the merge, so check a box only once the criterion is actually met. Numbered criteria are not recognized.
4. Check the title and body file before the push, which can take minutes:

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --preflight --title "<conventional commit title>" --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md"
   ```

   `--preflight` checks the title format and the body file name, mode, and marker.
   It makes no network call and creates nothing. The dash and escaped newline
   checks still run at step 7. Fix a rejection here.
5. Check that the body names only files the diff touches, before the push. The
   required `Validate PR` check fails on a path the diff does not touch, and the
   fix costs a CI round after the PR opens. Commit first: local mode reads
   committed `HEAD` only, so an uncommitted file reads as not in the diff. Run
   the local mode, which reads the same body file and
   `git diff origin/main...HEAD` with no network call:

   ```bash
   uv run --frozen python -I scripts/validation/pr_description.py --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md" --base origin/main
   ```

   - Exit 1 means a CRITICAL finding, usually `File mentioned but not in diff`.
     Stop. If every flagged path appears in `git status`, commit instead of
     editing the body. Otherwise edit the body file (remove the path, move it
     out of the change heading, or wrap it in a code fence), then re-run until
     it exits 0.
   - Exit 2 means the check could not run: an unreadable or non-UTF-8 body
     file, an unknown or invalid base ref, or git unavailable. For a missing
     `origin/main`, pass `--base` with the ref the PR targets, such as
     `<remote>/<default-branch>`. Do not skip the step.
   - Do not apply the `description-validation-bypass` label. A human maintainer
     decides that.
   - A checkout without `scripts/validation/pr_description.py`, such as a plugin
     install, cannot run this step. Say it was not run, and compare every
     path under the change heading (inline code, bold, list item, or link) to
     `git diff --name-only origin/main...HEAD` by hand.
6. Push the branch to origin.
7. Create a pull request using the new_pr skill script:

   <!-- vendor-portability: declared. This skill reads the consumer's
   `.github/PULL_REQUEST_TEMPLATE.md` and writes the consumer's
   `.project-toolkit/scratch/` body file. It resolves the helper from the installed
   Copilot or Claude plugin root. The `.claude` fallback is only for this
   repository's self-hosted source checkout; `scripts/pr/` is inside the
   shipped github skill, not the upstream-only top-level scripts/ tree.
   Issue #4764. -->

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --title "<conventional commit title>" --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md"
   ```

- Branch checked out in a worktree outside the clone, and the command runs from another checkout (for example the primary clone): append `--head "<branch>"`. Running the command from the worktree itself needs no `--head`, because `new_pr.py` uses the current branch. Never remove the worktree to open the PR. Push the branch first, since `gh` resolves the head on the remote. `new_pr.py` exits 2 and prints the push command when origin lacks the branch.
- A rejected body file names both rules at once: the file name pattern and mode 600. `--prepare-body-file` creates a file that meets both.
- Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
- Body SHOULD include GitHub issue linking keywords to auto-close issues:
  - `Closes #123`: auto-closes issue when PR merges
  - `Fixes #456`: auto-fixes issue when PR merges
  - `Resolves #789`: auto-resolves issue when PR merges
- Ensure PR template sections are completed

## Windows PR Body Fallback

Use this only on Windows, and only when step 3 exits 2 with
`ERROR: secure PR body files are not supported on Windows`. Every other
platform keeps the allocator mandatory. The allocator needs directory file
descriptors and owner-only modes that Windows does not provide.

`new_pr.py` accepts `--body '<text>'` in place of `--body-file`. That path
never calls the allocator or its file reader. The helper still runs the same
title, dash, and escaped newline checks, then hands the body to `gh` on
stdin, never as a command-line argument to `gh`.

1. Skip `--prepare-body-file`. Fill the PR template from step 2 into the body
   text yourself, with the same rules as step 3.
2. Step 4 preflight: pass `--body '<body text>'` instead of `--body-file`. It
   checks the title only, since there is no file to check.
3. Step 5: `pr_description.py --body-file` reads any readable file. Run
   `mkdir -p .project-toolkit/scratch` first, because the allocator refused
   before it created that directory. Create `pr-body-windows.md` in it with
   Write and expect one permission prompt. Later Edit fixes after a step 5
   exit 1 stay inside the scoped `Edit` grant.
4. Step 7: run the same command with the body text inline:

   ```bash
   python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py" --title "<conventional commit title>" --body '<body text>'
   ```

   - Paste the file's final contents, unchanged, as the `--body` text. Step 5
     checked the file, so every edit made there must reach this command.
   - Quote the body so the shell passes it literally. In bash or Git Bash,
     use single quotes and write each apostrophe as `'\''`. In PowerShell,
     use a single-quoted here-string (`@'` ... `'@`). Never use double quotes:
     bash runs each backtick code span as a command and expands `$name`, and
     PowerShell treats the backtick as an escape and also expands `$`.
   - Write the body literally in the command. Do not build it from a shell
     variable, for the same fresh-shell reason as step 3.
   - Use real line breaks inside the quoted text, never `\n`. If the escaped
     newline check fails, its message says to pass `--body-file`. That is the
     refused path on Windows, so fix the line breaks instead.
   - Windows caps a command line near 8191 characters in cmd.exe and 32767
     through CreateProcess. The body rides on argv twice: to `new_pr.py`, then
     to `validate_pr_description.py`. If the command fails for length, trim
     the body and keep every required template section.
   - Do not add `--skip-validation`. The fallback changes how the body arrives,
     not which checks it must pass.

You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.

## Verification

- [ ] Branch created off main when the working branch was main, never a push to main
- [ ] Title follows conventional commit format
- [ ] Local `pr_description.py --body-file` run exited 0 before the push, or its absence stated
- [ ] Body written into the allocator's returned path, copied exactly, never through a shell variable (Windows: the `--body` fallback, with step 5 still run)
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

- **Other forges.** Steps 3, 4, and 7 call `new_pr.py`. A non-GitHub forge swaps that
  helper; the template-adaptation rules in step 4 are forge-independent.
- **Template changes.** Step 4's section list follows the repository PR
  template read in step 3. When that template gains a parsed section, add it to
  step 4 and to the Verification list together.
- **Branch naming.** Step 1's conventional-type mapping is the repository
  convention; a project with a different scheme changes that sub-step alone.

<!-- vendor-portability: .project-toolkit/scratch is created in the consumer workspace
for one-run PR body files. It is not an upstream repository dependency. -->

<!-- vendor-portability-exec: step 5 runs scripts/validation/pr_description.py, an upstream-only validator the plugin install does not ship. Step 5 states the fallback. Issue #6405. -->
<!-- vendor-portability: step 5 reads scripts/validation/pr_description.py only when the consumer checkout carries it, and reports the step as not run otherwise. Issue #6405. -->
