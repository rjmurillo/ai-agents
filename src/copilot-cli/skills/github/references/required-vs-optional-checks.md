# Required Versus Optional PR Checks

Only a required check blocks a merge decision. An agent never waits on an
optional check. This page says which is which and how an agent treats each
kind.

One case needs an action but never a wait: a failed optional check whose
workflow is not in the advisory list. A repository's readiness gate can ask
for a recorded disposition for it. Record it, or fix the check.

## Which checks are required

The base branch ruleset is the only source. Read it live, through a script.
Never copy check names into prose, because a copied list drifts.

| Question | Command |
|---|---|
| Are the required checks green? | `get_pr_checks.py --pull-request N --required-only` and read `Data.RequiredState` |
| Wait for required checks only | Add `--wait --timeout-seconds 300` to the command above |
| Does the ruleset require any check? | Exit 0 with empty `Data.Checks` under `--required-only` means no. Classic protection may still require one, so re-run without the flag and require `AllPassing` |
| Can this PR merge? | `test_pr_merge_ready.py --pull-request N` and read `CanMerge` and `CIPassing` |
| Why is this PR blocked? | `why_pr_blocked.py --pull-request N` |

All three read the ruleset: `why_pr_blocked.py` through `github_core.branch_rules`,
the other two through `github_core.checks_rollup`, which wraps it. They mark each
check required or not, and they list a required check that never reported.

GitHub reports `mergeStateStatus: UNSTABLE` when every required check passed
and an optional check is failing or pending. `UNSTABLE` is mergeable.

## How to treat each kind

| Kind | Example | Blocks merge? | Agent action |
|---|---|---|---|
| Required check, failing or missing | A check the ruleset names | Yes | Fix it, or rerun a flake |
| Required check, pending | Still running | Yes, until it settles | Wait through the watcher |
| Optional check waiting on an environment approval | A job in an environment with required reviewers, state `WAITING` | No | Never wait. Never approve it yourself |
| Optional check in the advisory list | A workflow in `advisory_agent_workflows` | No, in any state, failed included | Read the result as review input |
| Optional check, failed, not in the advisory list | Any other non-required check | No wait. Needs a recorded disposition | Fix it, or record why in the dispositions file the readiness gate reads |
| Review bot, has not posted | Copilot, CodeRabbit, Cursor, Devin, and others | No | Never wait for it |
| Review bot, posted threads or `CHANGES_REQUESTED` | Same | Threads count like any reviewer's | Work them with `pr-comment-responder` |

The advisory list is `advisory_agent_workflows` in the pr-review skill's
`pr-review-config.yaml`. `test_pr_merge_ready.py` reads it from the trusted
ref, never from the PR branch, so a PR cannot exempt its own check.

The only bounded wait for bots is the 180-second settle in `pr-babysit`'s
`pr_wait.py`. It exists because bots often post 30 to 120 seconds after a
push. After it, a bot that has not posted holds nothing.

## Environment-gated runs

Only an environment's required reviewers can approve its deployment. An agent
never approves one, even when its token could.

When a gated run matters to the change, for example a plugin load smoke on a
change that touches plugin loading, run the same job locally. The workflow
file usually lists the local command in its header. Report the local result
in the PR body. Do not wait for the gated run.

## Merge gate wording

When a skill says "checks pass" or "review bots have finished", read it as:

- every required check passes on the current head;
- no required review is missing, and no posted review requests changes;
- every posted review thread is worked.

It never means "every check settled" or "every bot posted".
