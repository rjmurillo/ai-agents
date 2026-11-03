# Local hook or pre-push failure

Lefthook runs the pre-commit, commit-msg, pre-merge-commit, and pre-push gates
defined in [lefthook.yml](../../lefthook.yml). This runbook covers a commit or
push that a hook blocks.

## Symptom

- `git commit` or `git push` fails, and the output ends with a block that names
  the hook, each failed job, and a rerun command.
  `scripts/validation/lefthook_failure_report.py` prints that block.
- Every git command fails with `fatal: this operation must be run in a work tree`.
- Git reports a bad line in `packed-refs`.
- The hook does not run at all.

## Confirm

Check the hook install and the repository state. These commands only read state,
except `repair_packed_refs.py`, which removes blank lines from `packed-refs` when
it finds them and verifies refs after the rewrite:

```bash
uv run --frozen lefthook check-install
uv run --frozen python scripts/validation/check_git_hook_health.py
uv run --frozen python scripts/validation/check_repo_health.py
uv run --frozen python scripts/maintenance/repair_packed_refs.py
```

A healthy checkout prints `4 of 4 found` from the hook health check and
`none set true` from the repository health check.

## Recover

**A job failed.** Read the job output above the summary block. It names the file,
line, and finding. Fix the cause, then run the rerun command from the summary
block. It reruns only that job. For a pre-push job the command pipes the pushed
ref lines into the runner, in this shape:

```bash
printf '%s\n' '<ref lines>' | python3 scripts/validation/lefthook_runner.py run pre-push --job <job name> origin <remote url>
```

Copy the exact line from your output instead of typing it.

Run the full local gate before you push again:

```bash
uv run python scripts/validation/pre_pr.py
```

**The hooks are missing or stale.** Reinstall them:

```bash
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

**Git says the repository is bare.** Something set `core.bare = true` in a git
config scope. Run `check_repo_health.py` from the Confirm step and apply the
repair it prints. It names the scope that holds the bad value. The plain
`git config core.bare false` writes only the local config, so it cannot clear a
worktree, global, or system value. See
[GOTCHAS.md](../../.agents/governance/GOTCHAS.md) for the background.

**`packed-refs` has blank lines.** Run the repair command above. See
[Git packed-refs blank-line repair](../troubleshooting-packed-refs.md).

**The pre-push gate asks for a review marker.** Follow
[the review marker guide](../../.claude/skills/review/resources/marker-and-no-task.md).

Never bypass a hook with `--no-verify` or by changing the hook settings. If a
hook blocks you for a reason unrelated to your diff, hand off the branch with the
measured reason.

## Escalate

`lefthook.yml` and `scripts/validation/` belong to `@rjmurillo`
(`.github/CODEOWNERS`). Open an issue with the full failure block when a gate
fails on a clean `main` checkout.

## Links

- [CONTRIBUTING.md: Setup Steps](../../CONTRIBUTING.md#setup-steps)
- [GOTCHAS.md](../../.agents/governance/GOTCHAS.md)
