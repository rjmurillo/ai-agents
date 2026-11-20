# ai-agents-docs-of-record

Tells you which document of record to write for a piece of work, and how to write it: session logs, ADRs, retrospectives, Serena memories, and per-issue handoffs, with their templates, validators, and naming rules.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You need to pick where something goes: `which document of record does this go in`.
- You say `fill the retro` or `save this to memory`.
- You say `write the session log` (the skill tells you creation is discontinued and what to use instead).

## When not to use it

- You are writing an ADR: use [`adr-generator`](adr-generator.md) instead.
- You are authoring a skill: use [`skillforge`](skillforge.md) instead.
- You are writing up research: use [`ai-agents-research-methodology`](ai-agents-research-methodology.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-docs-of-record`. To ask for it by name, say:

```text
Use the ai-agents-docs-of-record skill to tell me which record to write for a decision that spans three sessions, and write it.
```

The agent picks the record from the situation table, follows the matching phase, and runs the linked validator.

## What you get

The right record in the right place. The skill's map lists each record's location, how to create it, and what validates it. Session log creation is discontinued, so continuity lives in per-issue handoffs and Serena memory. The skill also holds house prose style rules: lead with the point, name files and numbers, no em or en dashes.

## Advanced use

ADR numbers can collide when concurrent PRs pick the same next number, so treat a number as a claim and run the next-number instrument. For retrospectives, `reflect` captures corrections mid-conversation and `retrospective` produces the full artifact. Memory files follow the write conventions in the `memory` skill.

`instruments.py` lists and runs the linked checks: next ADR number, retro index coverage, session-log validation, and drift. Exit codes: 0 ok, 1 a listed file is missing, 2 bad arguments or unknown id, 3 the run target failed to start.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-docs-of-record/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-docs-of-record/scripts/instruments.py --repo . run adr-next-number
```

Replace `adr-next-number` with any instrument id. The ids are `adr-next-number`, `retro-index-coverage`, `session-log-validate`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`adr-generator`](adr-generator.md): authors an ADR.
- [`adr-review`](adr-review.md): debates an ADR when it changes.
- [`retrospective`](retrospective.md): the full retrospective artifact.
- [`reflect`](reflect.md): mid-conversation learning capture.
- [`memory`](memory.md): Serena memory write conventions.
- [`ai-agents-research-methodology`](ai-agents-research-methodology.md): research write-ups.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-docs-of-record/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
