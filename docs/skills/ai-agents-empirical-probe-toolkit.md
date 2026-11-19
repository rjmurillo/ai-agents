# ai-agents-empirical-probe-toolkit

A library of six recipes for replacing assumption with measurement in this repository. Each recipe has a worked example from repo history.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You are about to rely on undocumented tool behavior: `probe the runtime contract`.
- You are shipping a detector or threshold: `calibrate this guard`.
- You want proof, not argument: `prove it empirically`, `add a negative control`, `docs versus reality audit`.

## When not to use it

- You need the portability battle plan: use [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md) instead.
- You need evidence standards: use [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-empirical-probe-toolkit`. To ask for it by name, say:

```text
Use the ai-agents-empirical-probe-toolkit skill to calibrate the new push guard against the last five real PRs.
```

The agent picks the recipe from the selector table, follows its steps, and reports what would invalidate the result.

## What you get

A probe result or calibration table that you can cite. The six recipes are:

1. Runtime-contract probe
2. Guard and threshold calibration
3. Behavioral A/B via the eval harness
4. Docs-versus-reality audit
5. Reproduce-on-main discriminator
6. Negative-control test design

## Advanced use

A probe is a minimal disposable artifact run against the real pinned tool. The house rule is that a probe costs minutes and an assumption can cost an incident. A detector that cannot fire on recent real PRs is not calibrated.

`cli_flags_check.py` checks that eval-harness flags named in `SKILL.md` are declared by the script they belong to. It parses `add_argument` calls and never runs the scripts. Options: `--repo` and `--skill-md`. Exit codes: 0 every cited flag is declared, 1 an undeclared flag or missing script, 2 bad arguments or unreadable input.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-empirical-probe-toolkit/scripts/cli_flags_check.py --repo .
uv run python .claude/skills/ai-agents-empirical-probe-toolkit/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-empirical-probe-toolkit/scripts/instruments.py --repo . run eval-flags
```

Replace `eval-flags` with any instrument id. The ids are `eval-flags`, `cited-paths`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`agent-harness-reference`](agent-harness-reference.md): settled host contract facts.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): CI triage after the reproduce-on-main check.
- [`ai-agents-research-methodology`](ai-agents-research-methodology.md): where probes sit in the idea lifecycle.
- [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md): the evidence bar.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-empirical-probe-toolkit/SKILL.md)
- Reference: [`provenance.md`](../../.claude/skills/ai-agents-empirical-probe-toolkit/references/provenance.md)
- Reference: [`worked-examples.md`](../../.claude/skills/ai-agents-empirical-probe-toolkit/references/worked-examples.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
