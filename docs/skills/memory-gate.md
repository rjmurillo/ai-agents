# memory-gate

Forces a memory search before you change something that already exists. You recover why it exists, then decide to preserve, modify, or replace it. The gate is blocking, not advisory.

## When to use it

- You are about to change existing code, a constraint, or a protocol.
- You want the "why" behind a system before you remove it.
- Trigger phrases: `memory-first gate`, `search memory before changing`, `chesterton fence check`, `log this contradiction`.

## When not to use it

- You want a plain lookup with no pre-change gate: use [`memory-search`](memory-search.md).
- You want to record a finished session: use [`memory-reflexion`](memory-reflexion.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:memory-gate`. The agent loads it when your request matches, and [`spec`](spec.md) routes to it in Step 0. To ask for it by name, say:

```text
Use the memory-gate skill to check memory for why the retry limit in scripts/sync.py exists before I change it.
```

The skill uses project memory tools or repository files. It records the sources, results, and coverage gaps before the change proceeds.

## What you get

A recorded search that appears before the change decision, and a decision rationale that cites the memory findings. The skill's checks:

| Check | Evidence |
| --- | --- |
| Gate search ran | Result count is above 0, or "no results" was logged. |
| Ordering correct | The search appears before the change in the transcript, PR, handoff, or memory. |
| Escalation justified | Tier 2 was used only after Tier 1 came back thin. |
| Rationale recorded | The decision rationale cites the memory findings. |

The gate is blocking because advisory "check memory first" guidance had under 50% compliance. A skipped search is a failure.

## Advanced use

Match the change type to the search you need:

| Change type | Search |
| --- | --- |
| Remove an ADR constraint | `search_memory.py "[constraint name]"` |
| Bypass a protocol | `search_memory.py "[protocol name] why"` |
| Delete more than 100 lines | `search_memory.py "[component] purpose"` |
| Refactor complex code | `search_memory.py "[component] edge case"` |
| Change a workflow | `search_memory.py "[workflow] rationale"` |

Run the search from the root of a checkout of this repository:

```bash
uv run python .claude/skills/memory/scripts/search_memory.py "validation logic edge case"
```

The script belongs to the [`memory`](memory.md) router. This skill delegates to it and does not reimplement search. Start at Tier 1 (facts, patterns, constraints, ADR rationale). Escalate to Tier 2 (past session episodes) only when Tier 1 is not enough. Most checks resolve at Tier 1.

The skill applies the Chesterton's Fence idea: do not remove a fence until you know why it was put up. For the full four-phase investigation and decision matrix, use [`chestertons-fence`](chestertons-fence.md). Two references go deeper: [`agent-integration.md`](../../src/claude/skills/memory-gate/references/agent-integration.md) covers multi-agent patterns, and [`contradiction-log.md`](../../src/claude/skills/memory-gate/references/contradiction-log.md) covers logging a finding that contradicts conventional wisdom, including a measured result that disproves a memory or ADR. It writes a `decision-<slug>` entry to the repository memory store, Serena or not (ADR-126), and to a host-configured memory service when one exists.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`chestertons-fence`](chestertons-fence.md): the full four-phase investigation framework.
- [`memory-search`](memory-search.md): plain Tier 1 lookup.
- [`memory`](memory.md): the router that owns the search script.
- [`spec`](spec.md): routes here in Step 0.
- Source: [`SKILL.md`](../../src/claude/skills/memory-gate/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
