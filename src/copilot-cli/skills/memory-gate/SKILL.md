---
name: memory-gate
version: 0.1.0
description: Memory-First Gate (BLOCKING) and the Chesterton's Fence investigation
  protocol, split out of the memory router per ADR-063. Forces a memory search
  before you change existing code, constraints, or protocol, so the "why" is
  recovered before the fence comes down. Use when you say `memory-first gate`,
  `search memory before changing`, or `chesterton fence check`. Do NOT use for
  plain Tier 1 lookups (use memory-search) or recording a session (use
  memory-reflexion).
license: MIT
metadata:
  adr: ADR-007, ADR-037, ADR-063, ADR-070
  type: operation
  parent: memory
---

# Memory Gate

The Memory-First Gate and its investigation protocol, extracted from the
`memory` router per ADR-063 (memory-skill decomposition). `memory` still routes
here; an agent about to change an existing system loads this sub-skill instead
of the full memory surface.

The gate is one operation with a single rule: before you change something that
already exists, search memory for why it exists. The search uses the canonical
Tier 1 script; this sub-skill owns the enforcement semantics (ADR-070) and the
Chesterton's Fence framing, not the search implementation.

## Triggers

Use this skill when the user says:

- `memory-first gate` to apply the BLOCKING pre-change check
- `search memory before changing` to recover historical context first
- `chesterton fence check` to investigate why a system exists before removing it

## Memory-First Gate (BLOCKING)

Before changing existing systems, you MUST:

1. Search memory for the topic you are about to change.
2. Review results for historical context.
3. If Tier 1 is insufficient, escalate to Tier 2 (episodes).
4. Document findings in your decision rationale.
5. Only then proceed with the change.

```bash
# Recover the "why" before you change the "what"
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts"
python3 "$SCRIPTS_DIR/search_memory.py" "[topic]"
```

**Why BLOCKING**: under 50% compliance with "check memory first" guidance when it
is advisory. Making it BLOCKING achieves 100% compliance, the same pattern as
the session protocol gates (ADR-070 gate semantics).

**Verification**: the transcript, pull request, handoff, Serena memory, or an
optional log must show the search before the decision.

The canonical Tier 1 script is `search_memory.py`. It is shared with the
`memory` router and lives at
`.claude/skills/memory/scripts/search_memory.py`. This sub-skill delegates to it
and does not reimplement search.

## Memory-First as Chesterton's Fence

**Core insight**: memory-first architecture implements the Chesterton's Fence
principle for AI agents.

> "Do not remove a fence until you know why it was put up" (G.K. Chesterton)

**Translation for agents**: do not change code, architecture, or protocol until
you search memory for why it exists.

### Why this matters

**Without memory search** (removing the fence without investigation):

- Agent meets complex code, thinks "this is ugly, I will refactor it".
- Removes validation logic that guards an edge case.
- A production incident follows.
- Memory held the past incident that explained why the validation existed.

**With memory search** (Chesterton's Fence investigation):

- Agent meets complex code.
- Searches memory: `search_memory.py "validation logic edge case"`.
- Finds the past incident that explains why the code exists.
- Makes an informed decision: preserve, modify, or replace with equal safety.

## Investigation Protocol

When you want to change something that already exists, match the change type to
the required search:

| Change Type | Memory Search Required |
|-------------|------------------------|
| Remove ADR constraint | `search_memory.py "[constraint name]"` |
| Bypass protocol | `search_memory.py "[protocol name] why"` |
| Delete more than 100 lines | `search_memory.py "[component] purpose"` |
| Refactor complex code | `search_memory.py "[component] edge case"` |
| Change workflow | `search_memory.py "[workflow] rationale"` |

### What memory contains (git archaeology)

**Tier 1 (Semantic)**: facts, patterns, constraints.

- Why is Python the default for new internal automation? (ADR-042, which superseded the PowerShell-only ADR-005 but keeps PowerShell for quick fixes to existing PowerShell scripts and PowerShell-specific operations)
- Why did the PowerShell-only constraint exist, before it was superseded? (ADR-005, superseded by ADR-042)
- Why do skills exist instead of raw CLI? (usage-mandatory)
- What incidents led to BLOCKING gates? (protocol-blocking-gates)

**Tier 2 (Episodic)**: past session outcomes.

- What happened when we tried approach X? (session replay)
- What edge cases did we hit? (failure episodes)

Memory is your investigation tool. It holds the "why" that Chesterton's Fence
requires you to discover before you act. For the full four-phase decision
framework (Investigation, Understanding, Evaluation, Action) and the decision
matrix for when to investigate, use the [chestertons-fence
skill](../chestertons-fence/SKILL.md).

## Escalation

Tier 1 answers most "why does this exist" questions. Escalate when it does not:

```text
Change target identified?
│
├─► Tier 1: search_memory.py "[topic]"
│   └─► Facts, constraints, ADR rationale. Enough? Proceed.
│
└─► Not enough context? Escalate to Tier 2 (episodes)
    └─► What happened last time we touched this, and how did it end?
```

Escalate only when the cheaper tier is insufficient. Starting at Tier 1 keeps
the token cost low; most gate checks resolve there.

## Verification

| Operation | Verification |
|-----------|--------------|
| Gate search ran | Result count greater than 0 OR logged "no results" |
| Ordering correct | Search appears before the change in accepted evidence |
| Escalation justified | Tier 2 used only after Tier 1 came back thin |
| Rationale recorded | Decision rationale cites the memory findings |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Changing first, searching after | Search BEFORE the decision; log it before you act |
| Treating the gate as advisory | The gate is BLOCKING; a skipped search is a failure |
| Refactoring complex code blind | Search the component's edge cases before you touch it |
| Removing a constraint on sight | Search the constraint name; recover why it was set |
| Escalating straight to Tier 2 | Start at Tier 1; escalate only when it is thin |

## Process

### Phase 1: Identify

Name the existing system you intend to change and the change type. Match it to a
row in the Investigation Protocol table.

### Phase 2: Search

Run `search_memory.py` for the topic. Escalate to Tier 2 only when
Tier 1 is insufficient.

### Phase 3: Decide

Record the findings in your decision rationale, then preserve, modify, or replace
with equal safety. Never proceed with the change before the search is logged.

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory` | Router for search, reflexion, or maintenance operations |
| `memory-search` | Plain Tier 1 lookup with no pre-change gate semantics |
| `memory-reflexion` | Record a completed session as an episode |
| `chestertons-fence` | The full four-phase investigation framework and matrix |

## References

- ADR-007: Memory-first architecture (the posture this gate enforces)
- ADR-037: Memory router architecture (the router this sub-skill delegates from)
- ADR-063: Memory skill decomposition (this extraction)
- ADR-070: Gate semantics (why the gate is BLOCKING, not advisory)
- [references/agent-integration.md](references/agent-integration.md): multi-agent
  integration patterns, including the Memory-First Decision Making workflow this
  gate enforces
