---
status: proposed
date: 2026-04-21
decision-makers: rjmurillo-bot (autonomous agent)
consulted: architect, critic, independent-thinker (ADR review debate)
---

# ADR-058: Persistent Project Memory (MEMORY.md Pointer Index)

## Status

Proposed

## Date

2026-04-21

## Context

The ai-agents project already operates three memory systems: Serena (project-scoped, file-backed), Forgetful (cross-project, semantic), and Claude-Mem (session observations). ADR-007 established that retrieval precedes reasoning. ADR-017 defined a tiered index pattern for Serena's `.serena/memories/` catalog. `.agents/governance/MEMORY-MANAGEMENT.md` documents the three-tier workflow.

A gap remains. Narrative project knowledge that is (a) too broad for a single ADR, (b) too durable for a retrospective, and (c) required at the start of every session has no always-loaded home. Agents rediscover failure patterns, re-read retrospectives, or miss decisions buried in ADR history. Issue #1729 asks for a markdown-only pointer index that survives session resets and loads without an MCP call.

Both Claude Code (leaked three-layer memory, March 2026) and Copilot CLI solve this with a per-project markdown file that stores pointers, not data. Pointer-index discipline keeps the always-loaded surface small while keeping all knowledge navigable.

## Decision

Introduce `.agents/memory/MEMORY.md` as a markdown pointer index for persistent project memory.

1. `MEMORY.md` lists entries of the shape `- Topic description -> path/to/topic.md`. Entries are short (target 150 characters per line) and reference a file that exists.
2. Topic files live in `.agents/memory/` and follow a stable structure: Summary, What Failed / What Worked, Current Recommendation, References.
3. The index is additive. It does not replace Serena, Forgetful, or Claude-Mem. Content that fits those systems SHOULD go there; MEMORY.md is for cross-cutting project knowledge that every session benefits from seeing.
4. Write discipline: update `MEMORY.md` only after the referenced topic file is saved. Never point to a non-existent file.
5. Trust model: entries are hints, not ground truth. Agents verify against current code, ADRs, and retrospectives before acting on a recalled claim.

## Prior Art Investigation

### What Currently Exists

- **ADR-007**: Memory-first architecture (Serena + Forgetful). Retrieval before reasoning.
- **ADR-017**: Tiered memory index for `.serena/memories/` (pure lookup tables, domain indexes).
- **`.agents/governance/MEMORY-MANAGEMENT.md`**: Three-system workflow (Serena, Forgetful, Claude-Mem).
- **`.agents/retrospective/`**: Historical failure analyses.
- **`.agents/governance/FAILURE-MODES.md`**: Canonical failure pattern catalog.
- **`.agents/HANDOFF.md`**: Inter-session handoff (read-only per ADR-014).

### Historical Rationale

Serena's catalog optimizes for token-efficient lexical retrieval inside MCP. Forgetful provides semantic search across projects. Neither is loaded automatically at session start without a tool call. Retrospectives are authoritative but voluminous. An always-loaded, human-and-LLM readable index was never created because prior work focused on MCP-backed retrieval.

### Why Change Now

- Issue #1725 (structured handoff) and Issue #1726 (deterministic hooks) both assume a stable place to reference durable decisions.
- Post-compaction sessions lose in-conversation memory; they benefit from a small, always-loadable pointer index.
- The pointer-index pattern has observed adoption in Claude Code and Copilot CLI with reported retention gains.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Extend ADR-017 to cover markdown `.agents/memory/` | Single ADR, no duplication | ADR-017 targets Serena lexical retrieval; different loader, different lifecycle | Keeps cleaner separation; allows ADR-017 to remain focused |
| Store project memory in Serena only | No new files, leverages existing tooling | Requires MCP round-trip; not visible in plain `git diff`; not human-indexable | Loses the "always loaded, zero-tool-call" property |
| Inline knowledge in CLAUDE.md | Already always-loaded | CLAUDE.md is static rules, not evolving knowledge; bloats the base prompt | Mixes concerns; degrades prompt quality |
| Build now, wire hooks now | Complete in one PR | Adds blocking SESSION-PROTOCOL.md edit; widens adr-review scope | Deferred to #1726 per Issue #1729 "Why P2" |

### Trade-offs

The pointer index is additive surface area. It introduces a maintenance obligation: entries and files must stay in sync, and topic files must be refreshed as the codebase evolves. The offset is that post-compaction agents and new-session agents gain a small, reliable lookup table before making decisions.

## Consequences

### Positive

- Always-loaded access to cross-cutting project knowledge without an MCP call.
- Lower activation energy for "did we try this before?" questions.
- Visible in plain `git diff`; reviewable like any other markdown.
- Complements Serena (project), Forgetful (cross-project), and Claude-Mem (session) without replacing them.

### Negative

- New files to maintain; stale pointers are a recurring risk.
- Entry quality depends on authorship discipline; low-signal entries dilute the index.
- **Pre-hook trust-compliance window**: Until deterministic hooks land (#1726), MEMORY.md loading depends on agents following the prompt directive. This is the exact trust-based compliance pattern that `failure-trust-based-compliance.md` documents as degrading below 50%. Accepted risk per Issue #1729 "Why P2" rationale; detection: check session logs for MEMORY.md read evidence. If compliance drops below 70% over 5 sessions, escalate hook priority.

### Neutral

- Agent prompts (orchestrator, implementer) gain a short "Memory Update Protocol" section that directs when to write an entry and when not to.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/agents/orchestrator.md` | Direct | Follow-up: add explicit reference to MEMORY.md Memory Update Protocol section. Deferred to a later PR that produces ADR-057 behavioral eval evidence per the prompt-change gate. | Low |
| `.claude/agents/implementer.md` | Direct | Follow-up: same as orchestrator. | Low |
| `.agents/SESSION-PROTOCOL.md` | Indirect | Integration point documented here; actual gate wiring deferred to Issue #1726 hook infrastructure | Low |
| `.agents/HANDOFF.md` | Indirect | Structured handoff (#1725) may reference MEMORY.md entries | Low |
| `.agents/governance/MEMORY-MANAGEMENT.md` | Indirect | Future edit to describe MEMORY.md as the markdown Tier-0 layer | Low |

Deferring the SESSION-PROTOCOL.md edit is deliberate. Issue #1729 explicitly notes full value materializes after deterministic hooks land (#1726). Adding prompt-based "please load MEMORY.md" text without the hook produces the trust-based compliance failure pattern catalogued in `.agents/memory/failure-trust-based-compliance.md`.

## Reversibility Assessment

| Criterion | Status |
|-----------|--------|
| Rollback capability | Delete `.agents/memory/` directory and remove ADR-058; no other files depend on it yet |
| Vendor lock-in | None (pure markdown, git-tracked) |
| Exit strategy | Remove directory; existing Serena/Forgetful/Claude-Mem systems remain unaffected |
| Data migration | No data loss on rollback; topic file content sourced from existing FAILURE-MODES.md |
| Legacy impact | No existing system modified; MEMORY.md is additive-only |

## Implementation Notes

Initial content shipped with this ADR:

- `.agents/memory/MEMORY.md` (pointer index)
- Five failure-pattern topic files backfilled from `FAILURE-MODES.md`:
  - `failure-context-reading.md`
  - `failure-false-completion.md`
  - `failure-rubber-stamping.md`
  - `failure-premature-merge.md`
  - `failure-trust-based-compliance.md`

Memory Update Protocol location: the protocol is authored as a binding section inside `MEMORY.md` rather than copied into each agent prompt. Orchestrator and implementer inherit the protocol by reading `MEMORY.md` at session start. Inline references from `.claude/agents/orchestrator.md` and `.claude/agents/implementer.md` are deferred to a follow-up PR because editing agent prompt files triggers the ADR-057 behavioral evaluation gate; single-source-of-truth inside MEMORY.md avoids duplication drift and satisfies Issue #1729 AC #3 by making the protocol always-loaded for both agents.

Summary of the protocol (see MEMORY.md for the authoritative copy):

> Write a memory entry when: (a) a decision has non-obvious rationale, (b) a failure has been observed twice or more, (c) an investigation took longer than an hour to resolve. Do NOT write an entry for content already in CLAUDE.md, for temporary workarounds (use TODO), or for single-session scratch work. Update `MEMORY.md` only after the referenced topic file is saved.

## Related Decisions

- ADR-007 Memory-First Architecture
- ADR-008 Protocol Automation via Lifecycle Hooks
- ADR-014 Distributed Handoff Architecture
- ADR-017 Tiered Memory Index Architecture

## References

- Issue #1729 (this ADR)
- Issue #1725 Structured session handoff
- Issue #1726 Deterministic hook infrastructure
- `.agents/governance/FAILURE-MODES.md`
- `.agents/governance/MEMORY-MANAGEMENT.md`

---

*Template Version: 1.1*
