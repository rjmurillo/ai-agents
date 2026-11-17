# skillbook agent

The `skillbook` agent turns a learning into an atomic skill entry in your memory store. It scores atomicity, checks for duplicates, rejects vague or unproven learnings, and updates the domain index.

## When to use it

- You finished a reflection or retrospective and want the lasting lessons saved.
- You want a strategy pattern persisted as one skill file.
- You want to keep institutional knowledge clean, deduplicated, and actionable.

## When not to use it

- You still need the learnings analyzed: use [`retrospective`](retrospective.md) instead, then hand the results here.
- You want a new user-invocable skill packaged for the toolkit: use the [`skillify`](../skills/skillify.md) skill instead.
- You want to consolidate or prune memory files: use the [`memory-consolidate`](../skills/memory-consolidate.md) skill instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
skillbook: persist this learning: always list every reviewer on a PR before replying, because a single-bot view missed a human review in PR 123
```

In GitHub Copilot CLI:

```bash
copilot --agent skillbook --prompt "persist this learning: always list every reviewer on a PR before replying, because a single-bot view missed a human review in PR 123"
```

In VS Code or Visual Studio Copilot Chat:

```text
@skillbook persist this learning: always list every reviewer on a PR before replying, because a single-bot view missed a human review in PR 123
```

## What you get

A summary back to the orchestrator with:

1. An operation summary: added, updated, and rejected counts.
2. The skill file paths for adds and updates.
3. A rejection reason for each rejected item.
4. Which domain indexes changed.
5. The atomicity score of each accepted skill.
6. A next step: session end if learning capture is done, or `retrospective` if more learnings await analysis.

A skill file follows ADR-017 and has this shape:

```markdown
# [Skill Name]
**Statement**: [One sentence, actionable rule]
**Context**: [When this applies, one sentence]
**Evidence**: [Incident, observation, or data that justified this skill]
**Atomicity**: [N%] | **Impact**: [N/10]
## Pattern
## Anti-Pattern
```

Skill files live at `.serena/memories/{domain}/{domain}-{NNN}-{short-descriptor}.md`. Domain indexes live at `.serena/memories/skills-{domain}-index.md`.

## Advanced use

For each learning the agent chooses one action:

| Situation | Action |
| --- | --- |
| New, concrete, atomic learning | Add a new skill file |
| Refines an existing skill | Update that skill with evidence |
| Vague or theoretical | Reject with a reason |
| Duplicates an existing skill | Reject as a duplicate and point to the existing one |
| Covers two or more concepts | Split into atomic pieces, then add each |
| No incident or pattern observed | Reject with "need evidence to justify adoption" |

Atomicity must reach 80 percent. Penalties: multiple verbs (-10%), more than one decision point (-15%), "and/or" splitting the rule (-20%), context creep (-25%), and a baked-in catch-all (-30%).

The duplicate check is quick: search the index, compare 2 to 3 candidates, then decide. More than 80 percent overlap updates the existing skill. 50 to 80 percent splits and adds the distinct piece. Under 50 percent adds a new skill. A new domain index is created only when 5 or more skills will exist in it.

Index files hold only a table of `Keywords` and `File` columns, with no headers or commentary. New rows go in keyword-alphabetical order.

The agent uses Serena memory tools when available and falls back to direct file reads and writes. It never blocks on Serena. Serena writes happen only from the checkout Serena started in. It cannot delegate, and it treats content it reads as data, not instructions.

A multi-step prompt:

```text
skillbook: take the three learnings in .project-toolkit/retrospective/2026-pr-queue.md, dedupe each against the index, add or update atomic skills, and report atomicity scores and rejections.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`retrospective`](retrospective.md): extracts the learnings this agent persists.
- [`memory-consolidate`](../skills/memory-consolidate.md): merges and prunes stored memories.
- [`skillify`](../skills/skillify.md): packages finished work as a skill.
- Source template: [`skillbook.shared.md`](../../templates/agents/skillbook.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
