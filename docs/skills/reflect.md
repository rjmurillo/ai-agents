# reflect

Captures learnings from the current conversation and stores them as skill memory. It turns corrections, praise, and edge cases into confidence-labeled notes, and writes them only after you approve.

## When to use it

- You correct the agent's output ("no", "wrong", "not like that").
- You praise a specific output ("perfect", "exactly").
- The agent finds an edge case, or skill-heavy work is ending.
- A measured result contradicts a memory, ADR, skill, or common guidance. The skill points to the `memory-gate` contradiction log, even when the task ends at "do not ship".
- Trigger phrases: `reflect on this session`, `learn from this mistake`, `capture what we learned`, `improve skill {name}`, `what did we learn`.

## When not to use it

- You want a full session retrospective, or analysis across several sessions: use [`retrospective`](retrospective.md). This skill is the mini version.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:reflect`. The agent loads it when your request matches, and [`autoplan`](autoplan.md) routes a received correction or lesson here. To ask for it by name, say:

```text
Use the reflect skill to capture what we learned about the pr-review skill in this session.
```

The skill scans the conversation for learning signals, shows a confidence-labeled summary with the source quote for each, and waits for you to answer `Y`, `n`, or `edit`.

## What you get

A proposal with items labeled `[HIGH]`, `[MED]`, or `[LOW]`. After you approve, the skill adds dated observations and their sources to project memory. It preserves existing content and extracts code citations. It always shows changes before applying them.

| Check | Verification |
| --- | --- |
| Analysis complete | Signals are categorized by confidence. |
| You approved | An explicit `Y` or approval statement. |
| Memory updated | The approved entry exists in the selected project store. |
| Changes preserved | Existing content was not lost. |
| Commit ready | Changes are staged and a message is drafted. |

## Advanced use

The skill runs four phases:

1. **Identify the target skill.** Use `memory-search` or `memory` to find existing observations.
2. **Analyze the conversation.** Propose changes only when the threshold is met: at least 1 HIGH, 2 MED, or 3 LOW signals.
3. **Propose learnings.** Present the labeled summary and wait for approval.
4. **Persist.** Use [memory](memory.md) to update the record or save a Markdown note.

Serena writes go to the checkout where the server started. Do not call Serena write tools from a linked worktree. Edit the repository memory files in your own checkout, or hand the change to the parent session.

Priority tiers set invocation timing: HIGH (corrections and immediate fixes) invoke immediately, MEDIUM (praise, preferences, edge cases, questions) invoke once the threshold is met, and LOW (repeated patterns, session-end consolidation). The detail lives in the references:

- [`triggers.md`](../../src/claude/skills/reflect/references/triggers.md): priority-tiered trigger tables.
- [`phase2-signal-detection.md`](../../src/claude/skills/reflect/references/phase2-signal-detection.md): detection patterns and the threshold table.
- [`phase3-4-propose-persist.md`](../../src/claude/skills/reflect/references/phase3-4-propose-persist.md): proposal format, persistence, and memory format.
- [`decision-tree-and-examples.md`](../../src/claude/skills/reflect/references/decision-tree-and-examples.md): worked examples and anti-patterns.
- [`integration-and-design.md`](../../src/claude/skills/reflect/references/integration-and-design.md): integration, design decisions, and commit convention.

[`curating-memories`](curating-memories.md) takes over when conflicting or stale learnings need maintenance.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`retrospective`](retrospective.md): the full session retrospective.
- [`curating-memories`](curating-memories.md): maintains and prunes skill memories.
- [`memory`](memory.md): skill memories are part of Tier 1.
- [`autoplan`](autoplan.md): routes corrections here.
- Source: [`SKILL.md`](../../src/claude/skills/reflect/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
