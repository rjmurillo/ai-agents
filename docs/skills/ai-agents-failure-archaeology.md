# ai-agents-failure-archaeology

Records this repository's settled battles. Each major incident maps to a symptom, a root cause, an evidence path, and the artifact that fixed it, so you do not re-fight a decided question.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You ask whether something failed before: `has this failed before`, `why does this rule exist`.
- You want the history of a decision: `failure archaeology`, `what happened with the customer wedge`, `are we re-litigating a settled decision`.

## When not to use it

- You are triaging a live failure: use [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) instead.
- You want learnings from the current session: use [`retrospective`](retrospective.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In a Claude Code session inside this repository you can still type `/ai-agents-failure-archaeology`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the ai-agents-failure-archaeology skill to check whether weakening the push guard has been tried before.
```

The agent checks the major incidents table and the settled battles list, then reads the matching incident entry.

## What you get

The matching incident with its symptom, root cause, evidence path, and fix, or a statement that the question is not settled. Re-opening a settled position needs new evidence and the change-control path.

## Advanced use

If the tables do not answer, search retros by keyword (`grep -rli "<term>" .project-toolkit/retrospective/`) and do not rely on the retro `INDEX.md`, which lists only part of the corpus. New incidents map to the failure-mode catalog in `.agents/governance/FAILURE-MODES.md`.

`corpus_index.py` counts retros, reports which ones `INDEX.md` omits, lists failure modes, and counts memory files. `--shas SHA [SHA ...]` also reports whether short SHAs resolve locally. Exit 1 means `INDEX.md` omits retros, which is the normal state.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-failure-archaeology/scripts/corpus_index.py --repo .
uv run python .claude/skills/ai-agents-failure-archaeology/scripts/corpus_index.py --repo . --shas abc1234
uv run python .claude/skills/ai-agents-failure-archaeology/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-failure-archaeology/scripts/instruments.py --repo . run <id>
```

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-change-control`](ai-agents-change-control.md): the path for re-opening a settled rule.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): live triage.
- [`retrospective`](retrospective.md): capture learnings from the current session.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-failure-archaeology/SKILL.md)
- Reference: [`incidents.md`](../../.claude/skills/ai-agents-failure-archaeology/references/incidents.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
