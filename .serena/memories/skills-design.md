# Agent Design Skills

**Extracted**: 2025-12-16
**Source**: `.agents/governance/agent-design-principles.md`

## Skill-Design-001: Non-Overlapping Specialization (92%)

**Statement**: Each agent must have distinct purpose without duplicating another's responsibility

**Context**: Agent creation and review

**Evidence**: Agent consolidation process identified redundant agents requiring merger

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Detection**: Role overlap in agent definitions
**Fix**: Use consolidation process from governance

---

## Skill-Design-002: Clear Entry Criteria (90%)

**Statement**: Agents need explicit conditions for when to invoke them

**Context**: Agent definition and routing

**Evidence**: Vague routing caused orchestrator ambiguity in multi-agent workflows

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Detection**: Vague "use when" statements
**Fix**: Add concrete trigger scenarios with examples

---

## Skill-Design-003: Explicit Limitations (88%)

**Statement**: Agents must declare what they DON'T do to prevent misuse

**Context**: Agent definition and user expectations

**Evidence**: Agent interview protocol requires "What does it NOT do?" question

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Detection**: Missing "Constraints" section
**Fix**: Document anti-patterns and explicit boundaries

---

## Skill-Design-004: Composability (88%)

**Statement**: Agents should work in sequences without tight coupling

**Context**: Multi-agent workflows and handoffs

**Evidence**: Workflow skills demonstrate pipeline success with loosely coupled agents

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Detection**: Hard-coded agent names in outputs
**Fix**: Use handoff protocol with generic references

---

## Skill-Design-005: Verifiable Success (90%)

**Statement**: Every agent needs measurable completion criteria

**Context**: Agent definition and QA verification

**Evidence**: DoD skills show importance of explicit completion criteria

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Detection**: No output artifacts defined
**Fix**: Add expected deliverables with format/location

---

## Skill-Design-006: Consistent Interface (85%)

**Statement**: All agents follow same input/output contract

**Context**: Agent template enforcement

**Evidence**: Template generation process enforces consistent structure

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 7/10

**Detection**: Inconsistent prompt formats
**Fix**: Apply agent template strictly

---

## Skill-Design-009: Mermaid for AI-Parseable Diagrams (88%)

**Statement**: Use Mermaid for diagrams under 20 nodes; bullet lists for complex architectures

**Context**: Agent specification files, AGENTS.md, documentation requiring AI parsing

**Evidence**: Mermaid is 50% smaller than ASCII, self-healing on edits, dual-use for human/AI. Direct comparison: Mermaid flowchart 67 chars vs equivalent ASCII 140+ chars. ASCII breaks when node labels change; Mermaid regenerates clean output from syntax. AI correctly interprets Mermaid relationship semantics without visual rendering.

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 7/10

**Detection**: ASCII art diagrams in agent specs, diagrams with 20+ nodes as Mermaid
**Fix**: Convert ASCII to Mermaid for <20 nodes; use structured bullet lists for complex architectures

---

## Related Documents

- Source: `.agents/governance/agent-design-principles.md`
- Related: skills-workflow (handoff patterns)
- Related: skills-definition-of-done (completion criteria)
