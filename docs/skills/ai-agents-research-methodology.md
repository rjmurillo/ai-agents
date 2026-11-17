# ai-agents-research-methodology

Describes how a hunch becomes an accepted result in this repository: the evidence bar, predicting numbers before you measure, and a lifecycle with an artifact and a gate at each stage.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You ask how to prove an idea: `how do I prove this idea`, `turn this hunch into a result`.
- You want the lifecycle or the bar: `run the idea lifecycle`, `what is the evidence bar`.

## When not to use it

- You want the open research programs: use [`ai-agents-research-frontier`](ai-agents-research-frontier.md) instead.
- You want probe recipe depth: use [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In a Claude Code session inside this repository you can still type `/ai-agents-research-methodology`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the ai-agents-research-methodology skill to take my idea about a new push guard through the idea lifecycle.
```

The agent walks the lifecycle one stage at a time and records the artifact each stage needs.

## What you get

An accepted or retired idea with a complete artifact set. A result is accepted when one mechanism explains all observations, including the negative ones, and survives refutation. Retirement is recorded, never silenced.

## Advanced use

The lifecycle phases are: hunch, search, and contradiction log; spike with an empirical probe; capability gate and eval baseline; ADR and debate; ship as a gate or skill with calibration; monitor; adopt or retire with a record. Write the predicted outcome before you run a measurement, because a prediction made after the data is a description, not a test.

`instruments.py` lists and runs linked checks: a retro counter, a `file:line` claim check, `scripts/validation/check_citation_freshness.py`, and the drift check.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-research-methodology/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-research-methodology/scripts/instruments.py --repo . run <id>
```

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md): probe recipes.
- [`ai-agents-research-frontier`](ai-agents-research-frontier.md): what is worth researching.
- [`ai-agents-docs-of-record`](ai-agents-docs-of-record.md): templates and house style for write-ups.
- [`adr-generator`](adr-generator.md): author the ADR.
- [`adr-review`](adr-review.md): debate the ADR.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-research-methodology/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
