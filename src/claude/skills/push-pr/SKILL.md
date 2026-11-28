---
name: push-pr
version: 1.0.0
description: "Commit, push, and open a PR on GitHub or ADO with the repo template filled from the real diff. Use when you say `push and open a PR`, `open a pull request`, or `push this branch`, or when writing a push recipe or push lock file ($HOME/src/scratch/locks, the old /tmp lock). Do NOT use for pre-ship gates (use ship) or PR metadata validation alone (use validate-pr-description)."
license: Apache-2.0
allowed-tools: Bash(git checkout -b:*), Bash(git switch -c:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(python3:-I */pr/new_pr.py*), Bash(uv run --frozen python -I scripts/validation/pr_description.py*), Bash(git diff:*), Bash(git branch:*), Bash(python3:-I */pr/validate_pr_description.py*), Bash(mkdir:-p .project-toolkit/scratch), Edit(.project-toolkit/scratch/pr-body-*.md)
# Security note: python3 -I is the identity-hardened form.
# az is deliberately NOT granted. A prefix grant cannot limit its flags, so each ADO create prompts.
# git remote get-url is NOT granted. Its stdout can carry origin credentials, so host detection prompts.
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

Commit, push, and open a pull request, on GitHub or Azure DevOps, whose body is
adapted from the real diff rather than copied from the template. This skill is
the only place a PR is created; `/ship` calls it and never creates a PR itself.

Migrated from `.claude/commands/push-pr.md` under ADR-064, which makes skills the
single user-invocable surface. The scoped `allowed-tools` grant, the
identity-hardened `python3 -I` form, and both vendor-portability declarations
carry over unchanged: they are the security contract, not formatting.

## Triggers

`push and open a PR`, `open a pull request`, `push this branch`,
`commit and push`, `open an Azure DevOps PR`

## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`

## Host Detection

Run this before step 1. It sets `host`, which only step 7 branches on. Steps 1
to 6 run the same on both hosts.

```bash
remote_url="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$remote_url" ]; then
  echo "ERROR: origin remote is not configured; cannot detect VCS host." >&2
  exit 2
fi
case "$remote_url" in
  *dev.azure.com*|*visualstudio.com*) host=ado ;;
  *) host=github ;;
esac
redacted_remote_url="$(printf '%s' "$remote_url" | sed -E 's#(https://)[^/@]+@#\1[redacted]@#')"
echo "host=$host (origin: $redacted_remote_url)"
```

`dev.azure.com` or `visualstudio.com` anywhere in the URL means `host=ado`;
everything else is `host=github`. This is the same rule `/ship` uses.

## Commit Contract

Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.

When the working tree is clean, `/push-pr` MUST NOT create a commit. It pushes
`HEAD` as it stands. `/ship` relies on this: its owner-mode check requires the
tree to be clean after `/review`, so the push carries the reviewed marker commit
and nothing newer.

Folded rule: before you write, run, or quote a push lock or any command that serializes `git push`, read [push-lock](references/rule-push-lock.md).

## Process

Based on the above changes:

`<target>` is the branch the PR merges into: the repository default branch
unless the user names another. Steps 5 and 7 use it. Accept only a name made
of letters, digits, `.`, `_`, `/`, and `-`; otherwise stop and ask the user.

1. Create a new branch if on main.
   1. Determine the type of change that maps to a conventional commit type
      followed by a 3-5 word description (for example, `fix/parser-log-enrichment`).
2. Read @.github/PULL_REQUEST_TEMPLATE.md. Step 3 seeds it into the body file; use this copy only when the seeded file holds the marker alone.
3. Run the secure path allocator:

   ```bash
   ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 -I "$d/lib/ptk_run.py" skills/github/scripts/pr/new_pr.py --prepare-body-file; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
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
   ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 -I "$d/lib/ptk_run.py" skills/github/scripts/pr/new_pr.py --preflight --title "<conventional commit title>" --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
   ```

   `--preflight` checks the title format and the body file: its path, that it is a regular UTF-8 file, and that the placeholder line is gone.
   It makes no network call and creates nothing. On `host=github` the dash and
   escaped newline checks run at step 7. On `host=ado` the Azure DevOps
   section checks escaped newlines but not dashes, so it also requires a manual
   dash check. Fix a rejection here.
5. Check that the body names only files the diff touches, before the push. The
   required `Validate PR` check fails on a path the diff does not touch, and the
   fix costs a CI round after the PR opens. Commit first: local mode reads
   committed `HEAD` only, so an uncommitted file reads as not in the diff. Run
   the local mode, which reads the same body file and
   `git diff origin/<target>...HEAD` with no network call:

   ```bash
   uv run --frozen python -I scripts/validation/pr_description.py --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md" --base origin/<target>
   ```

   - Exit 1 means a CRITICAL finding, usually `File mentioned but not in diff`.
     Stop. If every flagged path appears in `git status`, commit instead of
     editing the body. Otherwise edit the body file (remove the path, move it
     out of the change heading, or wrap it in a code fence), then re-run until
     it exits 0.
   - Exit 2 means the check could not run: an unreadable or non-UTF-8 body
     file, an unknown or invalid base ref, or git unavailable. For a missing
     `origin/<target>`, pass `--base` with the remote ref that holds the
     target branch, such as `<remote>/<target>`. Do not skip the step.
   - Do not apply the `description-validation-bypass` label. A human maintainer
     decides that.
   - A checkout without `scripts/validation/pr_description.py`, such as a plugin
     install, cannot run this step. Say it was not run, and compare every
     path under the change heading (inline code, bold, list item, or link) to
     `git diff --name-only origin/<target>...HEAD` by hand.
6. Push the branch to origin.
7. Create the pull request. `host=ado` skips the rest of this step and follows
   Azure DevOps PR Creation. `host=github` uses the new_pr skill script:

   <!-- vendor-portability: declared. This skill reads the consumer's
   `.github/PULL_REQUEST_TEMPLATE.md` and writes the consumer's
   `.project-toolkit/scratch/` body file. It resolves the helper from the installed
   Copilot or Claude plugin root. The `.claude` fallback is only for this
   repository's self-hosted source checkout; `scripts/pr/` is inside the
   shipped github skill, not the upstream-only top-level scripts/ tree.
   -->

   ```bash
   ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 -I "$d/lib/ptk_run.py" skills/github/scripts/pr/new_pr.py --title "<conventional commit title>" --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
   ```

- `<target>` is not the default branch: add `--base "<target>"` inside the command, before its `; fi`, so the PR opens against the branch step 5 checked. Without it, `new_pr.py` targets the repository default branch.
- Branch checked out in a worktree outside the clone, and the command runs from another checkout (for example the primary clone): add `--head "<branch>"` inside the command, before its `; fi`. Words after the closing `)` run as a separate command. Running the command from the worktree itself needs no `--head`, because `new_pr.py` uses the current branch. Never remove the worktree to open the PR. Push the branch first, since `gh` resolves the head on the remote. `new_pr.py` exits 2 and prints the push command when origin lacks the branch.
- A rejected body file fails one of these checks: the path must resolve under the repo root, a temp directory, or the git dir; it must be a regular UTF-8 file; and it must no longer hold the `<!-- replace with PR body -->` line. `--prepare-body-file` creates a unique path that passes the path check.
- Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
- Body SHOULD include GitHub issue linking keywords to auto-close issues:
  - `Closes #<number>`: auto-closes issue when PR merges
  - `Fixes #<number>`: auto-fixes issue when PR merges
  - `Resolves #<number>`: auto-resolves issue when PR merges
- Ensure PR template sections are completed

## Azure DevOps PR Creation

Use this in place of step 7 only when `host=ado`. The `gh`-based `new_pr.py`
does not apply to Azure DevOps. Steps 1 to 6 still run: the body file comes from
step 3, the local checks from steps 4 and 5, and the push from step 6. Step 5
carries its own fallback when the local validator is absent, such as in a
plugin install.

First check the title and body with the offline description validator. It
needs no `gh` and makes no network call. Use the same title and body file
that passed steps 4 and 5:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 -I "$d/lib/ptk_run.py" skills/github/scripts/pr/validate_pr_description.py --title "<conventional commit title>" --body-file ".project-toolkit/scratch/pr-body-<returned-uuid>.md"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

Run it without `--fail-on-violation`, as `new_pr.py` does on GitHub. Warnings,
such as a missing `Closes #N` keyword or an Azure Boards `AB#` link, are
advisory: report them and go on. Exit 1 means escaped newlines in the body or
an unreadable body file. In this mode a bad title still exits 0, so also stop
when the output prints an `Errors` section. Step 4 already rejects a title that
is not a conventional commit. On either failure, fix the title or body file,
then re-run steps 4 and 5 and this check. Do not create the PR.

This validator has no dash check. Read the title and the body file for an em
dash (U+2014) or an en dash (U+2013). Replace each one before the create.

Then create the PR. `az` is not in `allowed-tools`, so this command prompts
the user, who sees every flag before it runs:

```bash
az repos pr create --output json --title "<conventional commit title>" --description '@<body-file-path-from-step-3>'
```

- Azure CLI replaces an argument that starts with `@` by the contents of that
  file, so `--description @<path>` sends the filled body file and never a shell
  variable.
- The path MUST be the exact body file path from step 3 that passed steps 4
  and 5, run from the same directory. No other argument may
  start with `@`: Azure CLI reads any `@<path>` argument from disk and sends the
  file to the server.
- The title MUST be the exact string that passed step 4 and this check. It MUST
  NOT start with `@`, and MUST NOT contain `"`, `$`, or a backtick. Azure CLI
  would read a title that starts with `@` as a file path.
- Run the command as shown. MUST NOT add any other flag, including
  `--auto-complete`, `--bypass-policy`, `--bypass-policy-reason`,
  `--delete-source-branch`, `--merge-commit-message`, `--org`, `--project`,
  `--repository`, `--reviewers`, `--required-reviewers`, `--work-items`,
  `--transition-work-items`, `--open`, or `--source-branch`. The one exception:
  add `--target-branch <branch>` only when the PR must not target the
  repository default branch. Then step 5 MUST have checked the paths against
  `origin/<branch>`, so the check read the same diff the PR shows. Run the
  validator with `--base origin/<branch>`, or, when the validator is absent,
  do the manual comparison against that branch.
- A non-zero exit means no PR was created. Report FAIL with the `az` stderr and
  stop. Never retry with a different command shape.
- On exit 0, check the `description` field of the JSON output. If it starts
  with `@`, Azure CLI could not read the body file and sent the path text
  instead. It does this silently, logging only at debug level. Report FAIL
  with the `pullRequestId` and ask the user whether to fix or abandon that PR.
  Do not abandon or edit it without their answer.
- Otherwise read `pullRequestId` from the JSON output. Report it, and the PR
  link `<repository.webUrl>/pullrequest/<pullRequestId>`, in the Output block.
- On Windows, the Windows PR Body Fallback replaces steps 3 to 5 only. Use
  `pr-body-windows.md`, the scratch file it creates for step 5, as the body
  file in both commands above. Skip its step 7 item. The `az`
  command stays the same. Keep the single quotes around `'@<path>'`:
  PowerShell reads an unquoted `@name` as splatting, not as text.

## Output

Finish with one line the caller can parse, naming the host and the PR:

```text
PR: host=github number=<number> url=<url>
PR: host=ado pullRequestId=<id> url=<url>
```

`/ship` reads `number` (GitHub) or `pullRequestId` (Azure DevOps) from this line
to check the pipeline on the new PR.

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
   ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 -I "$d/lib/ptk_run.py" skills/github/scripts/pr/new_pr.py --title "<conventional commit title>" --body '<body text>'; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
   ```

   - `<target>` is not the default branch: add `--base "<target>"` before the
     `; fi`, as in step 7.
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

## Verification

- [ ] Branch created off main when the working branch was main, never a push to main
- [ ] `host` detected from the origin URL, and `ado` created the PR with `az repos pr create`, never `new_pr.py`
- [ ] No commit created when the tree was already clean
- [ ] Title follows conventional commit format
- [ ] Local `pr_description.py --body-file` run exited 0 against `origin/<target>` before the push, or its absence stated
- [ ] GitHub PR opened against `<target>`, with `--base "<target>"` passed when it is not the default branch
- [ ] Body written into the allocator's returned path, copied exactly, never through a shell variable (Windows: the `--body` fallback, with step 5 still run)
- [ ] Every template section adapted from the real diff, with no placeholder comment left in
- [ ] An `## Acceptance criteria` heading present with `- [ ]` bullets, checked only where met
- [ ] Issue-linking keyword present, and a closing keyword used only when the diff delivers what the issue asks
- [ ] Output block names the host and the PR number (`pullRequestId` on ADO)

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Storing the allocator path in a shell variable | Each tool call runs a fresh shell, so the variable is empty on the next call and the body lands nowhere | Copy the returned path literally into the next call |
| Copying the template verbatim | Ships placeholder comments as the PR description, and the spec-coverage job reads them | Adapt every section from the diff |
| Numbered acceptance criteria | The Validate Spec Coverage job reads `- [ ]` and `* [ ]` only, so numbered items are invisible to it | Use checkbox bullets |
| Checking a criterion box before it is met | The signal reports a pass the PR does not have, and the FAIL it should have shown does not block merge | Check a box only once the criterion holds |
| Widening the `allowed-tools` grant to bare `Bash` | Removes the CWE-78 argument scoping that makes this skill safe to auto-approve | Add a specific scoped entry |
| Granting any `az` entry, including `az repos pr create:*`, for the ADO branch | A prefix grant auto-approves every flag, such as `--bypass-policy`, `--auto-complete`, or an `@<path>` that uploads a local file | Leave `az` ungranted so each create prompts |
| Creating a PR from `/ship` or any other skill | Splits title, body, and validation rules across two places | Call `/push-pr` and read its Output block |
| Committing when the tree is clean | Moves HEAD off the `/review` marker commit `/ship` verified | Push `HEAD` as it stands |

## Extension Points

- **Other forges.** Step 7 branches on `host`: `new_pr.py` for GitHub, `az repos pr create`
  for Azure DevOps. A further forge adds its own branch to Host Detection and step 7;
  the template-adaptation rules in step 3 are forge-independent.
- **Template changes.** Step 4's section list follows the repository PR
  template read in step 3. When that template gains a parsed section, add it to
  step 4 and to the Verification list together.
- **Branch naming.** Step 1's conventional-type mapping is the repository
  convention; a project with a different scheme changes that sub-step alone.

<!-- vendor-portability: .project-toolkit/scratch is created in the consumer workspace
for one-run PR body files. It is not an upstream repository dependency. -->

<!-- vendor-portability-exec: step 5 runs scripts/validation/pr_description.py, an upstream-only validator the plugin install does not ship. Step 5 states the fallback. -->
<!-- vendor-portability: step 5 reads scripts/validation/pr_description.py only when the consumer checkout carries it, and reports the step as not run otherwise. -->
