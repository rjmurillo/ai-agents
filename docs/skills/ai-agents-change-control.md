# ai-agents-change-control

Classifies a change in this repository, lists the gates that class triggers, and states the rules that never bend along with the incident behind each one.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You want to know what a change triggers: `classify this change`, `what gates does this change trigger`.
- You want the non-negotiable rules or the reason for one: `which rules are non-negotiable`, `why does this gate exist`.

## When not to use it

- You need to produce test evidence: use [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md) instead.
- You need incident history: use [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In a Claude Code session inside this repository you can still type `/ai-agents-change-control`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the ai-agents-change-control skill to classify my staged changes and list the gates they trigger.
```

The agent runs the classifier on your changed paths and lists the gates for each class. A mixed change inherits the gates of every class it touches.

## What you get

A class per changed path (docs-only, investigation-only, code, plugin content, hook, workflow, ADR governance) and the gates each class triggers. The classifier also reports allowlist violations. The skill adds a gate ladder, a table of non-negotiable rules with incidents, and anti-patterns.

## Advanced use

`classify_change.py` takes paths or reads them from git:

```bash
uv run python .claude/skills/ai-agents-change-control/scripts/classify_change.py --repo . --staged
uv run python .claude/skills/ai-agents-change-control/scripts/classify_change.py --repo . --base origin/main
uv run python .claude/skills/ai-agents-change-control/scripts/classify_change.py --map
```

`--staged` uses the staged files, `--base REF` uses `git diff --name-only REF...HEAD`, and `--map` prints the class-to-gate map. Exit codes: 0 ok, 1 allowlist violated, 2 bad arguments, 3 git failed. It does not read file contents or say whether a gate passes.

The gate ladder runs in feedback-cost order: pre-commit, then CI, then code review, then documentation. Catch problems at the first rung, for example with `uv run python scripts/validation/pre_pr.py` (`--quick` skips slow checks). `instruments.py` links the drift gates, the version-field gate, the dash check, citation freshness, and the allowlist.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-change-control/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-change-control/scripts/instruments.py --repo . run <id>
```

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md): produces the evidence the gates ask for.
- [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md): the history behind each rule.
- [`ai-agents-config-catalog`](ai-agents-config-catalog.md): escape hatches and when a bypass is allowed.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): what to do when a gate fails.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-change-control/SKILL.md)
- Reference: [`gate-ladder.md`](../../.claude/skills/ai-agents-change-control/references/gate-ladder.md)
- Reference: [`incident-history.md`](../../.claude/skills/ai-agents-change-control/references/incident-history.md)
- Reference: [`provenance.md`](../../.claude/skills/ai-agents-change-control/references/provenance.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
