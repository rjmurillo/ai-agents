# Local gates with Lefthook, and what to do when a hook blocks

## Goal

You will install the Git hooks, make one gate fail on purpose, read the failure
report, and clear it. The verified outcome: a commit that a hook blocked, then
the same commit accepted after you fix its message.

This page is a tutorial. It does not list every job. The authoritative list is
[lefthook.yml](../../lefthook.yml).

## Before you start

- A clean checkout of this repository with `uv` installed.
- Setup from [CONTRIBUTING.md: Setup Steps](../../CONTRIBUTING.md#setup-steps)
  finished through the dependency install.
- Bash or zsh. Step 3 prints an em dash from its UTF-8 bytes, so you do not type
  one.

## What runs, and when

Lefthook runs four Git hook stages.
[ADR-086](../../.project-toolkit/architecture/ADR-086-lefthook-local-hook-orchestration.md)
explains why Lefthook owns them.
[ADR-104](../../.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md)
sets where each check belongs and how long it may take.

| Stage | Runs when | Reads | Job timeouts in `lefthook.yml` |
|---|---|---|---|
| `commit-msg` | `git commit`, after you write the message | the message | 30s |
| `pre-commit` | `git commit`, before the message | the staged files | 5s to 10m per job, most 2m or 5m |
| `pre-merge-commit` | `git merge` that makes a merge commit | the staged files | 5s and 2m |
| `pre-push` | `git push` | the branch against `origin/main` | 10s to 30m per job |

ADR-104 states two time targets: 60 seconds per commit and 300 seconds per
push. Neither target is enforced at run time. A job timeout is a cap on one
job, not a promise of its speed. The ADR also notes the pre-commit target has
no measurement behind it. Lefthook skips a job when no staged file matches its
glob. On one workstation, an empty `git commit` that passed every gate took
1.08 seconds, a commit that staged one Markdown file took 7.9 seconds, and a
push of that one-file branch took 395 seconds.

Two rules of thumb from ADR-104:

- Pre-commit holds checks you fix in the same edit, such as formatting and
  prohibited characters.
- Pre-push holds checks that are cheap and would otherwise cost a CI round trip,
  such as ratchets, push-ref policy, and the tests that `pytest-testmon` picks.
  CI runs everything expensive.

## Steps

### 1. Install the hooks and check them

```bash
uv sync --frozen --extra dev
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

`check-install` prints nothing and exits 0 when the hooks match
`lefthook.yml`. Then confirm Git has all four hook files:

```bash
uv run --frozen python scripts/validation/check_git_hook_health.py
```

### 2. Start a practice branch

You will make commits you throw away. Keep them off your real branch:

```bash
git fetch origin
git switch -c practice/local-gates origin/main
```

### 3. Make a gate fail on purpose

The `commit-message-policy` job rejects an em dash (U+2014) or en dash (U+2013)
in a commit message. This command builds a message with an em dash without
typing one:

```bash
git commit --allow-empty -m "docs: tidy $(printf '\342\200\224') notes"
```

Git refuses the commit and prints this. `<git-dir>` stands for the absolute
path of your Git directory, which differs on your machine:

```text
ERROR: commit message contains em-dash (U+2014) or en-dash (U+2013)

exit status 1
lefthook_runner: commit-msg FAILED (exit 1)
  job: commit-message-policy
  rerun: uv run --frozen lefthook run commit-msg --job commit-message-policy <git-dir>/COMMIT_EDITMSG
  runbook: docs/runbooks/local-hook-failure.md
  rerun hook: uv run --frozen lefthook run commit-msg <git-dir>/COMMIT_EDITMSG
```

Confirm no commit was made:

```bash
git log --oneline -1
```

The top line is still the `origin/main` tip, not `docs: tidy`.

### 4. Read the failure report

The report has two parts.

1. The job's own output, above the summary. Here it is the `ERROR:` line. For a
   real finding it names the file, the line, and what is wrong. Fix this first.
2. The summary block from `scripts/validation/lefthook_failure_report.py`:
   - The first line names the stage that failed: `commit-msg`.
   - `job:` names each failed job.
   - `rerun:` reruns only that job, so you do not wait for the whole stage.
   - `rerun hook:` reruns the whole stage.
   - `runbook:` points at the recovery runbook.

### 5. Rerun only the failed job

Use `git rev-parse --git-path` for the message file instead of copying the
printed path. It works in a normal clone and in a linked worktree:

```bash
uv run --frozen lefthook run commit-msg --job commit-message-policy "$(git rev-parse --git-path COMMIT_EDITMSG)"
```

The job fails again, in a fraction of a second, and Lefthook lists it:

```text
ERROR: commit message contains em-dash (U+2014) or en-dash (U+2013)

exit status 1
🥊 commit-message-policy (0.19 seconds)
```

The rerun reproduces the block, so you can iterate on the fix without making
new commits. A wrong message path does not fail. The job passes when the file
is missing, so a mistyped path looks like a fix. Use the command above or copy
the line from your own output.

### 6. Fix the cause and commit

Write the message without the dash:

```bash
git commit --allow-empty -m "docs: tidy notes"
```

Git accepts the commit and prints a line like `[practice/local-gates 3fe854900] docs: tidy notes`.

### 7. Clean up

```bash
git switch -
git branch -D practice/local-gates
```

The practice commits were never pushed. `git reflog` still lists them until Git
expires the entries.

## Check your result

You are done when all of these hold:

- `uv run --frozen lefthook check-install` exits 0.
- The step 3 commit exited non-zero and made no commit.
- The step 6 commit exited 0.
- `git branch --list practice/local-gates` prints nothing.

## When it fails

Start with [the local hook failure runbook](../runbooks/local-hook-failure.md).
It covers a failed job, missing or stale hooks, `core.bare`, `packed-refs`, and
the pre-push review marker. This page does not repeat it.

Three cases come up most:

- **A job names your file.** Fix the file, rerun the printed `rerun:` command,
  then run `uv run python scripts/validation/pre_pr.py` before you push.
- **A pre-push job fails.** The `rerun:` line pipes the pushed ref lines into
  the runner. Copy it from your output. Do not retype it.
- **A hook blocks for a reason unrelated to your diff.** Check whether the gate
  also fails on a clean `main` checkout. If it does, hand off the branch with
  the measured reason: the stage, the job, the rerun output, and the commit it
  failed on. The runbook's Escalate section says where to file it.

Never use `git commit --no-verify` or `git push --no-verify`. Do not set
`LEFTHOOK=0` or edit `.git/hooks`. ADR-086 item 11 calls these local bypasses
and repository policy forbids using them to skip a required check. CI runs the
same checks and will block the pull request.

## Next

- [Local hook failure runbook](../runbooks/local-hook-failure.md): every
  recovery step, with commands.
- [CONTRIBUTING.md: Pre-Commit Hooks](../../CONTRIBUTING.md#pre-commit-hooks)
  and [Pre-Push Hooks](../../CONTRIBUTING.md#pre-push-hooks): how the shim
  resolves the Lefthook binary.
- [ADR-086](../../.project-toolkit/architecture/ADR-086-lefthook-local-hook-orchestration.md)
  and [ADR-104](../../.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md):
  the decisions behind the stages and the time targets.
