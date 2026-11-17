# context-gather

Collects what your project memory, library docs, repository docs, and the web already say about a topic. It returns a short summary so you can plan or build with context.

## When to use it

- You start a complex task that needs context from several sources before planning or implementation.
- You want framework guidance from Context7 next to what project memory records.
- You want to see what the memory tiers already hold on a topic before you choose an approach.
- Trigger phrases: `gather context for`, `what do we know about`, `gather context before planning`, `what do we know before I start`.

## When not to use it

- You want to compress or place skill text: use [`context-optimizer`](context-optimizer.md).
- The task is trivial and single-step.
- A `CONTEXT_LOADED: <topic>` line for the same topic is already in the conversation. The skill stops and reports `Context already loaded for <topic>`.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:context-gather`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the context-gather skill to gather context on pytest fixtures before I plan the test refactor.
```

The skill searches the knowledge tiers, then returns a focused summary with code snippets, file paths, and gaps.

## What you get

A summary that includes relevant code snippets and file paths, architectural insights and ADR references, framework-specific guidance when it applies, and the gaps that remain.

The output carries two marker lines:

| Marker | Meaning |
| --- | --- |
| `TIER_QUERIED: <tier>` | One line per tier the skill queried. The tier is `serena`, `context7`, `deepwiki`, or `web`. |
| `CONTEXT_LOADED: <topic>` | The last line. The topic is a short label such as `pytest-fixtures`. |

Only this skill reads the `CONTEXT_LOADED:` marker. Its first phase scans the conversation for one and skips a repeat fetch for the same topic.

## Advanced use

The skill runs in three phases:

1. Scan the conversation for a `CONTEXT_LOADED:` marker. If the topic matches, stop.
2. Search the tiers, in parallel where possible: Serena memory first, then Context7 for known libraries, then DeepWiki for repository docs, then the web only when the others fall short. The skill stops early once coverage is sufficient. [`references/context-retrieval.md`](../../src/claude/skills/context-gather/references/context-retrieval.md) holds the source priority, the untrusted-content guard, and the synthesis and citation rules.
3. Synthesize a summary, emit the marker, and return it.

The skill does not pin a model. It inherits the harness default, because retrieval is search and synthesis work.

The quality gate: the summary addresses the stated topic, at least one queried tier is reconciled (a short-circuit or early stop is exempt), and the marker line is present. The skill does not return raw tool output.

The [`autoplan`](autoplan.md) skill routes unfamiliar-topic requests here before [`research`](research.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`autoplan`](autoplan.md): routes unfamiliar topics to this skill.
- [`research`](research.md): the step that follows context gathering.
- [`steering-matcher`](steering-matcher.md): a sibling preflight skill in the `/build` chain.
- [`chestertons-fence`](chestertons-fence.md): a sibling preflight skill in the `/build` chain.
- Source: [`SKILL.md`](../../src/claude/skills/context-gather/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
