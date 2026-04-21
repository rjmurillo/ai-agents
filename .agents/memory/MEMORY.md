# ai-agents Project Memory

> **Purpose**: Always-loaded pointer index to persistent project knowledge. Each entry stores a LOCATION, not data. Topic files are fetched on demand.
> **Load policy**: Read at session start alongside `.agents/HANDOFF.md`. Fetch a linked topic file only when the current task touches its subject.
> **Write discipline**: Update an entry ONLY after the topic file it points to has been written and saved. Never list a file that does not exist.
> **Trust model**: Entries are hints, not ground truth. Verify against the current codebase, ADRs, and retrospectives before acting.
> **Scope**: Narrative project knowledge (decisions, failure patterns, conventions) too broad for a single ADR and too durable for a retrospective. Does NOT replace Serena, Forgetful, or Claude-Mem (see `.agents/governance/MEMORY-MANAGEMENT.md`).

## Known Failure Patterns

- Context reading failure (session-start non-compliance, 95.8% baseline) -> `failure-context-reading.md`
- False completion markers (agents reporting "done" when incomplete) -> `failure-false-completion.md`
- Multi-agent rubber-stamping (parallel reviewers converging on approval) -> `failure-rubber-stamping.md`
- Premature merge and deploy (PR #226 incident pattern) -> `failure-premature-merge.md`
- Trust-based compliance degradation (<50% without verification gates) -> `failure-trust-based-compliance.md`

## Architecture Decisions at a Glance

- Memory-first architecture (retrieval before reasoning) -> ADR-007, `.agents/architecture/ADR-007-memory-first-architecture.md`
- Tiered Serena memory index (pure lookup tables) -> ADR-017, `.agents/architecture/ADR-017-tiered-memory-index-architecture.md`
- Protocol automation via lifecycle hooks (not prompts) -> ADR-008, `.agents/architecture/ADR-008-protocol-automation-lifecycle-hooks.md`
- Distributed handoff architecture (HANDOFF.md is read-only) -> ADR-014, `.agents/architecture/ADR-014-distributed-handoff-architecture.md`
- Persistent markdown project memory (this index) -> ADR-058, `.agents/architecture/ADR-058-persistent-project-memory.md`

## Conventions That Bit Us

- PR description format: issue-linking keywords, conventional commit titles, no internal path refs in `src/` -> see `.claude/skills/validate-pr-description/` and Issue #1711.
- Session-end gate compliance (evidence required, auto-populated by skill) -> `.claude/skills/session-end/`.

## What NOT to Re-Research

- Raw `gh` commands in Claude sessions -> BLOCKED by hook; use `.claude/skills/github/` scripts. AGENTS.md "Boundaries" > "Never".
- Rewriting `.agents/HANDOFF.md` in an agent session -> PROHIBITED per ADR-014. Use session logs and `.agents/handoffs/` artifacts instead.
- Logic inside GitHub Actions YAML -> PROHIBITED per ADR-006. Delegate to testable scripts.

## Integration Points

- **Hooks (Issue #1726)**: `SessionStart` hook SHOULD surface MEMORY.md loading status once deterministic hook infrastructure lands.
- **Handoff (Issue #1725)**: Structured handoff documents SHOULD reference relevant MEMORY.md entries under "decisions made" and "open questions".
- **Session Protocol**: `.agents/SESSION-PROTOCOL.md` retains authority over gate semantics. MEMORY.md is additive context, not a new gate.

## Memory Update Protocol (binding for orchestrator and implementer)

This section is always loaded at session start. Orchestrator and implementer prompts inherit it by reading `MEMORY.md`. Inline prompt-file edits are a follow-up once ADR-057 behavioral eval evidence is produced. See ADR-058.

**Write a topic file when**:

- A decision has non-obvious rationale that outlives a single ADR entry.
- A failure pattern has been observed twice or more.
- An investigation took longer than one hour to resolve.

**Do NOT write a topic file when**:

- The content already lives in `CLAUDE.md`, `AGENTS.md`, or an ADR (link, don't copy).
- The item is a temporary workaround (use a TODO comment in the code instead).
- The scope is a single session with no cross-session value.

**Strict write discipline**: update an entry in `MEMORY.md` ONLY after the referenced topic file is saved. Never list a file that does not exist. If the file write fails, do not touch the index.

**Verification over trust**: entries are hints, not ground truth. Before acting on a recalled claim, verify against current code, ADRs, and retrospectives. A stale pointer is worse than no pointer.

**Topic file format** (Summary -> What Failed / What Worked -> Current Recommendation -> References). Keep the active surface minimal; detail lives in referenced files.
