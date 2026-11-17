# ai-agents-diagnostics-toolkit

Catalogs the instruments that measure this repository, each with its command, a baseline, and a guide to reading the number. You get a number to compare instead of a guess.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You want to measure skill size, description budgets, drift, orphan references, or coverage pins: `measure this`, `check skill budgets`.
- You need to read a scan or drift signal: `read the drift signal`, `interpret this scan output`.

## When not to use it

- You need to fix what an instrument found: use [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) instead.
- You need evidence standards for tests: use [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In a Claude Code session inside this repository you can still type `/ai-agents-diagnostics-toolkit`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the ai-agents-diagnostics-toolkit skill to measure the skill description budget and compare it to the baseline.
```

The agent picks the instrument, runs it from the repo root, and reads the result against the baseline in the guide.

## What you get

A number per instrument and a reading: green and unchanged, red where the baseline was green (your change caused it), or red where the baseline was already red (flag it, keep your delta clean). The Instrument Index lists the question each instrument answers and its command.

## Advanced use

`baseline_snapshot.py` prints the headline numbers of the four read-only instruments (description budget, skill size, orphan references, golden principles) as JSON. Exit 0 means every instrument produced numbers, and 1 means one ran but its output could not be read.

Use `uv run python`, not a bare interpreter, for anything that imports repo modules, because PyYAML lives in the venv. The skill says every instrument leaves the trees it measures unchanged, with one documented exception: `build_all.py --check` writes a gitignored audit file outside those trees.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-diagnostics-toolkit/scripts/baseline_snapshot.py --repo .
uv run python .claude/skills/ai-agents-diagnostics-toolkit/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-diagnostics-toolkit/scripts/instruments.py --repo . run description-budget
```

Replace `description-budget` with any instrument id. The ids are `description-budget`, `skill-size`, `orphan-refs`, `golden-principles`, `agent-drift`, `build-check`, `install-parity`, `eval-prompt-change`, `eval-agent-vs-baseline`, `coverage`, `commit-count`, `baseline-snapshot`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): fix what an instrument surfaces.
- [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md): evidence standards.
- [`orphan-ref-validator`](orphan-ref-validator.md): the orphan-reference scan.
- [`golden-principles`](golden-principles.md): the golden-principles scan.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-diagnostics-toolkit/SKILL.md)
- Reference: [`instrument-guides.md`](../../.claude/skills/ai-agents-diagnostics-toolkit/references/instrument-guides.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
