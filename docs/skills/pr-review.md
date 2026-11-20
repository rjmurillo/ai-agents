# pr-review

Answers the review comments on one or more pull requests, then runs a completion gate that tells you whether each PR can merge. It runs [`pr-comment-responder`](pr-comment-responder.md) once per PR and prints a summary table.

## When to use it

- You have review comments on a PR and want a merge verdict at the end.
- You have comments on several PRs and want one run to cover them.
- Trigger phrases: `/pr-review 1234`, `/pr-review 12 15 --parallel`, `respond to review comments and tell me if it can merge`, `address the review feedback`, `handle the bot comments on my PR`.

## When not to use it

- A check is red and there are no review comments: use [`pr-autofix`](pr-autofix.md).
- You want to work one PR's threads and need no gate verdict: use [`pr-comment-responder`](pr-comment-responder.md).
- You want to watch a PR until CI and review settle: use [`pr-babysit`](pr-babysit.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-review 1234
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-review 1234`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /pr-review skill to ...`.

To preview without changing anything, add `--dry-run`. The skill prints its planned actions as JSON and exits.

## What you get

- Every review thread gets a reply. A reply alone does not resolve a thread. Only bot-authored or explicitly approved threads are resolved, never in bulk while a human thread is open. A question stays open until the reviewer answers. See [`pr-comment-responder`](pr-comment-responder.md).
- A summary table with one row per PR, in the format set by `pr-review-config.yaml`.
- A completion-gate verdict per PR, run once.

The completion gate runs each criterion in the config as an external command. The command's JSON output decides the verdict.

| Gate exit | Meaning |
| --- | --- |
| `0` | Every criterion passed |
| `1` | At least one criterion failed. The skill shows the criterion's name, command, reason, and an output excerpt, then stops. |
| `2` | Config error, including a config that differs from the trusted ref |
| `3` | The trust check could not run, or the verdict is `unknown` |

After a failure, the skill does not re-run the gate for a different answer. It fixes the cause first, then runs the gate once more.

## Advanced use

### Arguments

| Argument | Description | Default |
| --- | --- | --- |
| `PR_NUMBERS` | One or more PR numbers, such as `12 15`, or `all-open` | Required |
| `--parallel` | Use git worktrees so PRs run in parallel | `false` |
| `--cleanup` | Remove worktrees when done | `true` |
| `--dry-run` | Preview planned actions as JSON, no changes | `false` |

`all-open` is capped by `invocation_limits.all_open_max_prs` in the config (default 5). The skill reports the overflow count and applies `invocation_limits.all_open_overflow_action`.

### Steps

1. **Step 0, trust and transport.** Runs `run_completion_gate.py --verify-config-only` once, before any command from the config. It executes nothing. Then it checks whether `gh` is usable. A transport failure is never reported as a PR verdict.
2. **Step 1, validate PRs.** Skips merged PRs.
3. **Step 2, status.** Runs Phase 0 thread clustering, reads every thread and comment, checks mergeability and failing checks. After the last thread resolves, `wait_for_settled_zero` needs three clean readings 180 seconds apart. Bot scans can land 30 to 120 seconds after a push.
4. **Step 3, worktrees** (only with `--parallel`). They go in a sibling of the checkout, never under it and never under `/tmp`.
5. **Step 4, launch.** Runs `pr-comment-responder` per PR with a `Transport: gh` or `Transport: gh_unusable` line. Parallel runs use background agents.
6. **Steps 5 and 6.** Push, clean up, and print the summary.

### Trust boundary

The gate refuses to run if `pr-review-config.yaml`, or a file its commands name, differs from the trusted ref (`origin/main` by default). The ref must be a remote-tracking ref. A human must read the diff before anyone passes `--approve-untrusted-config`. That flag never applies to an exit-3 halt. Read [`trust-boundary.md`](../../src/claude/skills/pr-review/references/trust-boundary.md) before you approve.

The gate parses YAML. If PyYAML is missing, it exits 2 with a clear message. Run it with `uv run --with pyyaml python ...`.

### Gate script

Run this from the root of a checkout of this repository:

```bash
uv run python .claude/skills/github/scripts/pr/run_completion_gate.py --help
```

Flags: `--config`, `--pull-request` (required), `--json`, `--evidence-path`, `--trusted-ref`, `--verify-config-only`, `--harness`, `--approve-untrusted-config`. `--harness` needs `--verify-config-only` and takes `claude_code` or `copilot`.

### Late review rounds

After round 1, a new thread counts only if the diff introduced the defect or a claimed acceptance criterion is unmet. Otherwise the reply is `[WONTFIX]` and the thread goes under "Flagged notes" in the summary.

### Extending it

Add completion criteria as entries in `completion_criteria`. Each names a command whose JSON output is the verdict. Installed consumers replace the shipped criteria with their own and keep the dispatcher.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pr-comment-responder`](pr-comment-responder.md): does the per-PR thread work.
- [`pr-autofix`](pr-autofix.md): fixes red checks across PRs.
- [`pr-babysit`](pr-babysit.md): watches one PR until it is ready.
- [`github`](github.md): owns the scripts the gate calls.
- Source: [`SKILL.md`](../../src/claude/skills/pr-review/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
