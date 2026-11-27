# pr-autofix

Walks your open pull requests, sorts them into tiers, fixes failing CI and unresolved review threads, and enables auto-merge only when a four-condition Ready-to-Merge gate passes. It checks live PR state before every change, so it does not act on a stale snapshot.

## When to use it

- You want open PRs triaged and worked in bulk: land-ready first, then CI fixes, then review threads.
- You want one PR on your current branch fixed through to merge.
- You want periodic triage that does not merge. Say `monitor open prs` for that mode. The no-argument and PR-number forms can merge or turn on auto-merge.
- Trigger phrases: `pr-autofix`, `autofix this pr`, `monitor open prs`, `auto-merge ready prs`, `address pr feedback`.

## When not to use it

- You want to watch a single PR: use [`pr-babysit`](pr-babysit.md) instead.
- You want to answer one PR's review comments: use [`pr-review`](pr-review.md) instead.
- You want to run the quality axes before pushing: use [`pr-quality`](pr-quality.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-autofix 1234
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-autofix`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /pr-autofix skill to ...`.

The argument is a pull request or a mode. With no argument the skill triages every open PR. For each PR it classifies a tier, checks the live state, acts, and reports. It stops and hands the PR to a human when it cannot prove the PR is safe to act on.

## What you get

Each PR ends in one outcome: fixed and merged (or armed for auto-merge), handed to a human with a reason, or skipped. The skill sorts PRs into tiers using `test_pr_merge_ready.py`.

| Tier or state | Meaning | Action |
| --- | --- | --- |
| `T1` | Mergeable (`CLEAN`, `HAS_HOOKS`, or `UNSTABLE` with disposed non-required failures), targets the default branch | Merge by the path for its `mergeStateStatus` |
| `T2` | CI failures only | Fix CI, verify required checks pass |
| `T3` | Unresolved threads only | Walk the thread lifecycle, then merge |
| `T4` | CI failures and threads | Fix CI first, then the threads |
| `T5` | Bot-authored PR with failures or threads | Handed to a human |
| `BEHIND` | Branch behind the base, only while the ruleset requires up-to-date branches | Update the branch, then reclassify |
| `BLOCKED` | Waiting on an outside gate, with no failure or thread | Run the stale bot review detector, then wait |
| `DIRTY` | Merge conflict | Resolve with the [`merge-resolver`](merge-resolver.md) skill or agent, then reclassify |
| `SKIP` | Draft, merged, or closed | No action |
| `UNSUPPORTED` | A `mergeStateStatus` with no verified merge path | Disarm auto-merge, hand to a human |
| `STACKED` | Would be `T1` but targets a non-default branch | Disarm auto-merge, hand to a human |

A PR is ready to merge only when all four conditions hold:

1. No merge conflict with `main` (`mergeStateStatus` is not `DIRTY`). Being behind `main` does not count against it.
2. All required checks pass.
3. Every conversation is read, triaged, solved if blocking, replied to with a course of action, and resolved.
4. `mergeStateStatus` is `CLEAN` or `HAS_HOOKS`, or `UNSTABLE` with documented non-required failures.

`CanMerge=True` from `test_pr_merge_ready.py` is one input, not the decision.

The merge path depends on state:

| `mergeStateStatus` | Path |
| --- | --- |
| `CLEAN` or `HAS_HOOKS` | `set_pr_auto_merge.py --enable`, then `merge_pr.py --strategy squash` if GitHub rejects an already-clean PR |
| `UNSTABLE` with documented non-required failures | `merge_pr.py --strategy squash` |

> [!WARNING]
> After every merge the skill lands, it reads [`references/post-merge-cleanup.md`](../../src/claude/skills/pr-autofix/references/post-merge-cleanup.md) before it removes the PR worktree or deletes the local branch.

## Advanced use

### Gates that run before any change

1. **Transport preflight** (phase 0). It runs `check_github_transport.py` once. `Transport: gh` continues. `Transport: gh_unusable` continues in MCP mode, where the readiness, round-cap, and triage scripts have no MCP equivalent and their verdicts are derived by hand and recorded as derived. Exit 3 means stop and retry later. Exit 4 means a credential fault: stop and report it.
2. **Live-state gate.** `check_pr_live_state.py` returns `Data.action` of `ACT` or `SKIP`. `SKIP` is binding: no push, no auto-merge, no `merge_pr.py`. The gate captures the head SHA, base ref, and base SHA.
3. **Late live-state wrapper.** Every mutation (base refresh, merge, rebase, push, auto-merge change, thread reply or resolve, direct merge) runs through `run_pr_mutation_if_live`. It re-queries GitHub just before the command and compares against the captured identity. Exit 75 means it skipped the mutation.
4. **Auto-merge disarm gate.** If auto-merge is armed and the PR is not provably `T1` (including a `T1` whose `fetched_pages_complete` was not boolean `true`), the skill runs `set_pr_auto_merge.py --disable` before any push.
5. **Round-cap circuit breaker** (`T3` and `T4` only). `check_pr_round_cap.py` returns `ACT` or `ESCALATE`. Defaults are 5 rounds and 4 hours. Override them with `--max-rounds`, `--max-hours`, `PR_AUTOFIX_MAX_ROUNDS`, or `PR_AUTOFIX_MAX_ROUND_HOURS`. On `ESCALATE` the script posts its own PR comment and the loop stops. A maintainer restarts it with a `/pr-autofix continue` comment, or by running the script with `--reset`. The disarm gate runs before the breaker so an escalated PR is never left with auto-merge armed.

An author the skill cannot classify is treated as a bot (fail closed), so it does not enter the unattended loop.

### CI failure triage

For each failing check, run `triage_red_check.py --check-name "<name>" --pull-request <n>` before reading any log.

| Verdict | Exit | Meaning |
| --- | --- | --- |
| `RED_ON_MAIN` | 1 | Inherited from `main`. Cite the `EvidenceUrl`, do not debug the PR |
| `GREEN_ON_MAIN` | 0 | The PR introduced it. Read the logs |
| `PR_ONLY` | 3 | The check never reports on `main`. Read the PR run |
| `CANCELLED_ON_MAIN` | 3 | No completed evidence on `main`. Rerun the `EvidenceRunId` run |
| `UNKNOWN` | 3 | Probe failure, never evidence of green |
| `Error.Type` `NotFound` | 3 | The branch was not found. Fix `--branch`, do not rerun |

### Stale bot review

A PR can stay `BLOCKED` after every thread is resolved because a bot holds an old `CHANGES_REQUESTED` review. Run `detect_stale_bot_review.py` on such a PR. It posts nothing and returns a `Data.verdict`.

| Verdict | Action |
| --- | --- |
| `NO_BOT_CHANGES_REQUESTED` | The block is another outside gate. Stop |
| `NOT_READY` | Finish the open work listed in `Data.reasons`, then run it again |
| `FRESH_CHANGES_REQUESTED` | Address the findings through the thread lifecycle |
| `REQUEST_REREVIEW` | Post each bot's `rereview_trigger` once per head SHA, then run it again |
| `DISMISSAL_HANDOFF` | Give `Data.handoff` to a human verbatim and stop |

The skill never dismisses a review. A nonzero exit is an unknown, never a verdict.

### Force-push safety

Before any push, `git rev-parse "refs/heads/$BRANCH"` must match the PR's expected `head.sha`. A force-push needs explicit user authorization and an SHA-pinned lease: `--force-with-lease="refs/heads/${BRANCH}:${EXPECTED_REMOTE_SHA}"` with `FORCE_PUSH_OK=1`. A bare `--force-with-lease` is not allowed. It reads a tracking ref that any `git fetch` can advance. The skill never skips git hooks.

### Completion gate

`run_completion_gate.py` runs after threads resolve and CI passes. Its exit codes:

| Exit | Meaning |
| --- | --- |
| 0 | All criteria passed |
| 1 | A criterion failed |
| 2 | Config error, including a `pr-review-config.yaml` that diverges from or is absent at `origin/main` |
| 3 | No payload: trust verification was impossible. With `verdict: unknown`: the session refuses GitHub, so check the rows in `unknown_criteria` by hand |

Do not retry exit 2 or exit 3. Do not pass `--approve-untrusted-config` autonomously. A human reads the surfaced diff first, and the flag cannot override an exit-3 halt.

### Scripts

The PR scripts ship with the `github` skill. From the root of a checkout of this repository:

```bash
uv run python .claude/skills/github/scripts/pr/check_pr_round_cap.py --help
uv run python .claude/skills/github/scripts/pr/detect_stale_bot_review.py --help
```

`check_pr_round_cap.py` takes `--pull-request`, `--max-rounds`, `--max-hours`, `--reset`, `--worktree`, `--dry-run`, and `--output-format`. `detect_stale_bot_review.py` takes `--pull-request` and `--output-format`. The other scripts the skill calls are `test_pr_merge_ready.py`, `check_pr_live_state.py`, `get_pr_context.py`, `set_pr_auto_merge.py`, `merge_pr.py`, `add_pr_review_thread_reply.py`, `triage_red_check.py`, and `run_completion_gate.py`.

### References

Three procedures load on demand from `references/`:

- `post-merge-cleanup.md`: worktree and branch removal after a merge.
- `merge-check-exit-codes.md`: the `test_pr_merged.py` exit-code contract. Branch on its JSON `merged` field, not the exit code.
- `extension-points.md`: read it when you change the tier set, merge-state rows, round budget, or concurrency boundary.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pr-babysit`](pr-babysit.md): watch one PR.
- [`pr-review`](pr-review.md): answer one PR's review comments and run the completion gate. It redirects a red check with no review comments to this skill.
- [`pr-quality`](pr-quality.md): run the quality axes before you push.
- [`merge-resolver`](merge-resolver.md): resolve a real merge conflict on a `DIRTY` PR.
- [`github`](github.md): provides the PR scripts and the transport preflight.
- Source: [`SKILL.md`](../../src/claude/skills/pr-autofix/SKILL.md)
- Reference: [`post-merge-cleanup.md`](../../src/claude/skills/pr-autofix/references/post-merge-cleanup.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
