# Design: Mermaid For Aiparseable Diagrams 88

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

## Related

- [design-001-nonoverlapping-specialization-92](design-001-nonoverlapping-specialization-92.md)
- [design-002-clear-entry-criteria-90](design-002-clear-entry-criteria-90.md)
- [design-003-explicit-limitations-88](design-003-explicit-limitations-88.md)
- [design-004-composability-88](design-004-composability-88.md)
- [design-005-verifiable-success-90](design-005-verifiable-success-90.md)
