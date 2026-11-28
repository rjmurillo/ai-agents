# pr-babysit

Watches one pull request from push to ready. It handles each real event (a failed check, a new review, a conflict) and stays quiet between events. It uses one event-driven watcher and no polling loop.

## When to use it

- You pushed a PR and want it carried through CI and review.
- You want to be told when the PR is ready, not to check on it.
- Trigger phrases: `babysit this PR`, `watch this PR`, `monitor this PR until green`, `wait for checks and reviews`, `wait for ci`.

## When not to use it

- You have many PRs: use [`pr-autofix`](pr-autofix.md).
- You want to reply to review threads: use [`pr-comment-responder`](pr-comment-responder.md). `pr-babysit` calls it for you.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-babysit 1234 --until ready
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-babysit 1234 --until ready`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /pr-babysit skill to ...`.

The argument is a PR number or URL. `--until` is `ready` (default), `green`, or `any-change`.

## What you get

When the PR is ready, the skill says so. It merges only if you asked it to. It sends no "still waiting" messages between events.

The watcher, `pr_wait.py`, prints one line per real event and nothing else on stdout. The event words are `head`, `check`, `green`, `comment`, `review`, `thread`, `activity`, `base`, `merge-state`, `ready`, `blocked`, `merged`, `closed`, and `unreachable`.

| Exit | Meaning | Next step |
| --- | --- | --- |
| `0` | The `--until` condition is met, or the PR merged | Recheck the merge gate on the current head |
| `1` | A new blocker: a failed or missing required check, DIRTY, closed, or (for `ready`) unresolved threads, BEHIND, draft, or a review requirement | Act, push, start the watcher again |
| `2` | Bad input, another watcher on this PR, `gh` not on PATH, or a bad `why_pr_blocked.py` payload | Fix the input. Do not start a second watcher. |
| `3` | The PR does not exist (a `not found:` line, never retried), or GitHub was unreachable for 10 polls in a row | Fix the PR number. For an outage, check the rate limit, then start again. |
| `4` | `gh` is not authenticated | Sign in to `gh`, then start again |

## Advanced use

### Phases

1. Handle what exists now: fix real failures and work threads with `pr-comment-responder`.
2. Wait for the next event with one watcher.
3. Act on each event with a fix, a written reason, or no action. Then wait again.

### Watcher choices

- In T3 Code, call `watch_pull_request` with the full PR URL and end your turn. Only the thread that owns the PR watches it. Call `unwatch_pull_request` before you hand off. The tool reports conflicts, not BEHIND, so check BEHIND yourself.
- On other hosts, run `pr_wait.py` under the host's background-run tool. In Claude Code that is `Monitor` with `timeout_ms: 1800000`. On a host that cannot stream lines, use `--until any-change` so each event ends the run.
- Never write your own `sleep` loop. Never run two watchers on one PR.

### `--until` modes

| Mode | Exits when |
| --- | --- |
| `ready` | Required checks pass, no unresolved thread, no required or changes-requested review, and the branch is not BEHIND, DIRTY, or a draft. It also waits 3 minutes after it first sees a head. |
| `green` | Required checks pass. |
| `any-change` | Same rules as `ready`, but it also exits on the first event. |

A required check counts as never reported only 45 minutes after the watcher first saw the head. A blocker only a person can clear exits 1 once. The restarted watcher then waits for it quietly. State is kept per PR for 6 hours.

### Script

Run this from the root of a checkout of this repository:

```bash
uv run python .claude/skills/pr-babysit/scripts/pr_wait.py --help
```

Flags: `pr` (positional), `--repo OWNER/NAME`, `--until {ready,green,any-change}`, `--interval SECONDS` (default 30, floor 10). Between reads it waits on `gh event listen` when gh is 2.105.0 or later and the account has GitHub Event Streams access, and wakes at the next review, push, merge conflict, finished check suite, or state change. Otherwise it sleeps `--interval`. Output and exit codes match on both paths. A `pr-event-wait:` line on stderr names the mode and why listening stopped, and `AI_AGENTS_PR_EVENT_LISTEN=0` forces the sleep. The skill also ships `pr_wait_activity.py` and `pr_wait_state.py` as helpers for the watcher.

### Merging

The merge gate is the [`github`](github.md) skill's `test_pr_merge_ready.py` on the latest head. A watcher exit 0 is the cue to run it, not a pass. Merge only when you asked for it. Never merge when the PR is BEHIND or DIRTY. Update with `update_pr_branch.py` or merge the base locally. Never force-push a shared branch.

### Reviews and scope

Act only on checks and comments newer than the latest push. Verify each bot finding against the source. Rerun infrastructure flakes with `rerun_failed_jobs.py`. Decline low-value fixes with a written reason and list them as follow-ups, so the PR stays the size your goal needs. Never wait for advisory bots.

### Rate limits

GraphQL and REST have separate budgets. Read the remaining budget with the `github` skill before you watch again. Never guess a reset time.

The watcher reads the newest 100 review threads. On a PR with more, it says so once. Read every thread with `pr-comment-responder` before you call the PR ready.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

On Muse Code, which documents no background shell tool, the watcher runs as one long foreground call.

## Related

- [`pr-comment-responder`](pr-comment-responder.md): owns thread replies and resolution.
- [`pr-autofix`](pr-autofix.md): handles many PRs.
- [`pr-review`](pr-review.md): answers comments and gives a completion verdict.
- [`github`](github.md): provides the merge gate and rerun scripts.
- Source: [`SKILL.md`](../../src/claude/skills/pr-babysit/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
