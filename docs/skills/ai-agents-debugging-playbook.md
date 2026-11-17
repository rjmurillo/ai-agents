# ai-agents-debugging-playbook

Maps a recurring failure in this repository to a first command, a discriminating experiment, a fix path, and the trap that has already cost someone time.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- A push is blocked, a drift gate is red, the plugin bump gate is red, a coverage pin tripped, a hook exited 143, or a session was marked NON_COMPLIANT.
- You say `triage this failure`, `why is my push blocked`, `debug this CI red`, `what does this gate failure mean`, or `hook blocked my tool call`.

## When not to use it

- You want the full history of an incident: use [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md) instead.
- You want to measure something: use [`ai-agents-diagnostics-toolkit`](ai-agents-diagnostics-toolkit.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-debugging-playbook`. To ask for it by name, say:

```text
Use the ai-agents-debugging-playbook skill to triage why my push to this branch was rejected by a guard.
```

The agent matches your symptom to a table row, runs its first command, and runs the discriminating experiment before it proposes a fix.

## What you get

A named cause for the failure, a fix applied on the canonical surface only, and a local re-run of the exact failing check. The tables cover local blocks, CI reds, shared-checkout problems with many worktrees, and Copilot CLI runtime failures.

## Advanced use

The first question for any CI red is whether the same job fails on main. If it does, it is not your branch. The skill asks three questions before any fix: does it reproduce on main, is the gate working or broken, and, for a drift red, which tree is canonical. Do not edit until you can answer the last one from [`AGENTS.md`](../../AGENTS.md) or the generator docstring.

`first_command.py` covers the shared-checkout rows:

| Subcommand | Does |
| --- | --- |
| `stash` | Marks each stash entry as own or foreign |
| `lag` | Prints left and right counts of `BASE...HEAD` (`--base BASE`). It does not fetch, so run `git fetch origin main` first |

`instruments.py` links the plugin version gate, the dash scan, spec id uniqueness, the Python syntax gate, the CI drift step, and the drift self-check.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-debugging-playbook/scripts/first_command.py --repo . stash
uv run python .claude/skills/ai-agents-debugging-playbook/scripts/first_command.py --repo . lag --base origin/main
uv run python .claude/skills/ai-agents-debugging-playbook/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-debugging-playbook/scripts/instruments.py --repo . run first-command-stash
```

Replace `first-command-stash` with any instrument id. The ids are `first-command-stash`, `first-command-lag`, `plugin-version-bump`, `dash-scan`, `spec-id-uniqueness`, `python-syntax`, `drift-ci`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md): history of the incidents behind each row.
- [`ai-agents-diagnostics-toolkit`](ai-agents-diagnostics-toolkit.md): numbers and baselines.
- [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md): the reproduce-on-main recipe.
- [`git-advanced-workflows`](git-advanced-workflows.md): worktree and shared-state caveats.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-debugging-playbook/SKILL.md)
- Reference: [`vacuous-gates.md`](../../.claude/skills/ai-agents-debugging-playbook/references/vacuous-gates.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
