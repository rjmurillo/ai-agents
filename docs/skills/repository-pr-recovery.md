# repository-pr-recovery

Attributes why a pull request in this repository is blocked, why a required check is missing, or why a baseline was cancelled. It picks the smallest legitimate recovery action.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- A PR is stuck: `recover a blocked ai-agents PR`.
- A check is red and you need its cause: `attribute an ai-agents red check`.
- A required check never reports: `required check never reports`.

## When not to use it

- You need completion proof: use [`repository-completion-proof`](repository-completion-proof.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In a Claude Code session inside this repository you can still type `/repository-pr-recovery`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the repository-pr-recovery skill to find out why PR 1234 is blocked and whether its red check also fails on main.
```

The agent finds the blocker, classifies a failed check against main, joins the check to the required producer, and returns the evidence and the next authorized action.

## What you get

A report with the blocker, attribution, revision, evidence URL, owner, and next authorized action. The red-check triage returns one verdict:

| Verdict | Meaning |
| --- | --- |
| `GREEN_ON_MAIN` | Reproduce the alleged regression on the PR |
| `RED_ON_MAIN` | Inherited failure; compare signatures and report the evidence URL |
| `PR_ONLY` | No matching row in the examined history; read the PR run logs |
| `CANCELLED_ON_MAIN` | Identify the workflow and attempt; ask for an authorized rerun |
| `UNKNOWN` | Resolve the missing evidence first |

## Advanced use

`required_check_producer_join.py` joins check-runs to the required status checks of a base branch. It reads through the GitHub client with GET calls only:

```bash
uv run python .claude/skills/repository-pr-recovery/scripts/required_check_producer_join.py --repo . --pr 123
uv run python .claude/skills/repository-pr-recovery/scripts/required_check_producer_join.py --repo . --sha "$(git rev-parse HEAD)" --base main
```

Each required context reads `produced-by-the-required-app`, `produced-by-another-app`, or `missing`. Exit 0 means all produced, 1 a finding, 2 bad arguments, 3 a failed or incomplete read. It does not read legacy commit statuses or merge queues.

`instruments.py` ids: `why-pr-blocked`, `triage-red-check`, `check-logs`, `review-threads`, `required-context-conditions`, `producer-join`, `drift-self-check`. Pass extra arguments after `--`, for example `run triage-red-check -- --history-depth N` (maximum 50 commits).

Policy changes and bypasses are outside this skill. A successful diagnosis does not mean the PR is accepted or merged.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/repository-pr-recovery/scripts/instruments.py --repo . list
uv run python .claude/skills/repository-pr-recovery/scripts/instruments.py --repo . run drift-self-check
```

Replace `drift-self-check` with any instrument id. The ids are `why-pr-blocked`, `triage-red-check`, `check-logs`, `review-threads`, `required-context-conditions`, `producer-join`, `drift-self-check`. `list` prints each one with the question it answers. Some instruments need more arguments after `--`; `list` shows each one's command.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`repository-completion-proof`](repository-completion-proof.md): the next step once the blocker clears.
- [`github`](github.md): GitHub transport and scripts.
- [`reviewer-findings`](reviewer-findings.md): verify review findings.
- [`pr-comment-responder`](pr-comment-responder.md): reply to review threads.
- Source: [`SKILL.md`](../../.claude/skills/repository-pr-recovery/SKILL.md)
- Reference: [`evaluation.md`](../../.claude/skills/repository-pr-recovery/references/evaluation.md)
- Reference: [`library.md`](../../.claude/skills/repository-pr-recovery/references/library.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
