# memory-documentary

Builds a cited, evidence-based report on a topic by searching all your memory systems, project artifacts, and GitHub issues. The report reads like investigative analysis, and every claim carries a source, a date, and a direct quote.

## When to use it

- You need cross-system evidence for a pattern or recurring theme.
- You want to see how your thinking or a decision changed over time.
- You want a verifiable narrative built from memory data.
- Trigger phrases: `Search my memories for patterns about...`, `What does my history say about...`, `Generate a documentary on my topic`, `Cross-reference all systems for...`, `Evidence-based analysis across memory systems`.

## When not to use it

- You want one fact or pattern from a single memory tier: use [`memory`](memory.md).
- You want citation hygiene on existing memories: use [`memory-enhancement`](memory-enhancement.md).

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:memory-documentary`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the memory-documentary skill to write a report on recurring frustrations with test flakiness, starting from 2025-12-01.
```

The skill plans queries per system, collects evidence, writes the report, and stores the meta-pattern it found.

## What you get

A report saved to `.project-toolkit/analysis/[topic]-documentary-[date].md` with these sections:

| Section | Content |
| --- | --- |
| Executive Summary | Key finding in one sentence, timeline span, evidence count, major pattern categories. |
| Evidence Trail | For each finding: source system, retrieval key with its command, date, direct quote, links to related evidence. |
| Pattern Evolution | A dated timeline of how thinking changed. |
| Unexpected Patterns | Frequency, correlation, avoidance, contradiction, evolution, and emotional patterns. |
| Synthesis | What all systems agree on, what is recent (Claude-Mem) versus durable (Serena), and recommendations. |

Every claim has a retrieval key, a date, and a direct quote. The skill does not paraphrase.

## Advanced use

The skill runs five phases: topic comprehension, investigation planning, data collection, report generation, and a memory update that stores the meta-pattern.

It searches these sources:

- Memory systems: Claude-Mem (timeline observations), Serena (project lexical memory), and DeepWiki (documentation).
- Project artifacts under `.project-toolkit/`: `retrospective/`, `sessions/`, `analysis/`, `architecture/`, and `planning/`.
- GitHub issues: open and closed, with comments and related PRs.

Use at least three query variants per system. Search all three systems, or record any that were unavailable. In a vendored install without the `.project-toolkit/` tree, the report uses whatever memory systems and artifacts the repository has.

The source documents an optional time range, written as `--since 2025-12-01` after the topic. The full execution protocol is in [`references/execution-protocol.md`](../../src/claude/skills/memory-documentary/references/execution-protocol.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory`](memory.md): the router that sends cross-system report requests here.
- [`retrospective`](retrospective.md): learning extraction.
- [`skillbook`](../agents/skillbook.md): converts a pattern into a skill.
- Source: [`SKILL.md`](../../src/claude/skills/memory-documentary/SKILL.md)
- Reference: [`execution-protocol.md`](../../src/claude/skills/memory-documentary/references/execution-protocol.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
