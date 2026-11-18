# ai-agents-research-frontier

Lists three ranked open research programs for this repository. Each has current-state evidence, first concrete steps, and a milestone that could fail.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You ask what to research next: `research frontier`, `open problems`, `what should we research next`, `frontier programs`.

## When not to use it

- You want to know how to run an experiment here: use [`ai-agents-research-methodology`](ai-agents-research-methodology.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-research-frontier`. To ask for it by name, say:

```text
Use the ai-agents-research-frontier skill to tell me which research program to start and what its first step is.
```

The agent re-verifies the current state, picks the highest-ranked program with an unclaimed step, and lists its first steps.

## What you get

A chosen program, its three first steps, and a falsifiable milestone. The programs are verified governance (ADR-069, proposed), cross-harness abstraction (ADR-072 and ADR-068), and the self-improving loop. The rank order is owner-confirmed.

## Advanced use

Each step that produces a measurement must predict the number before the run. Results go through the normal machinery: write-ups by `ai-agents-docs-of-record`, changes by `ai-agents-change-control`, and ADR edits fire the `adr-review` debate gate. A negative result is a result. A new idea that fits no program is a new capability and goes through the buy-versus-build gate.

`instruments.py` runs `corpus-counts` (JSON counts of skills, rules, rule-scenario fixtures, retros, and memory files) and `corpus-index`. `corpus-index` exits 1 while the retro `INDEX.md` omits retros, so a non-zero exit does not mean a broken skill.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-research-frontier/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-research-frontier/scripts/instruments.py --repo . run corpus-counts
```

Replace `corpus-counts` with any instrument id. The ids are `corpus-counts`, `corpus-index`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-research-methodology`](ai-agents-research-methodology.md): the discipline for running an idea.
- [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md): the hook portability battle plan.
- [`buy-vs-build-framework`](buy-vs-build-framework.md): the gate for a new capability.
- [`adr-review`](adr-review.md): debate gate for ADR edits.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-research-frontier/SKILL.md)
- Reference: [`program3-self-improving-loop.md`](../../.claude/skills/ai-agents-research-frontier/references/program3-self-improving-loop.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
