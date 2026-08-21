---
id: ADR-NNN
status: proposed
date: YYYY-MM-DD
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: null           # optional: YYYY-MM-DD this record must be revisited; null when the decision carries no deadline
---

# ADR-NNN: [Title]

<!--
Lifecycle state lives in the frontmatter above and nowhere else. This template
carried `## Status` and `## Date` prose sections until 2026-08-21; both restated
frontmatter fields verbatim, and every record generated from it inherited the
duplication. Two review comments on PR #5209 (ADR-005 "Duplicative. Already in
frontmatter", ADR-024 "Redundant") rejected it.

The rule: prose says what frontmatter cannot, and never restates what it carries.

Add a prose section only when it carries something the enum cannot, such as
review evidence, provenance, or the condition blocking acceptance. Name it for
what it holds (`## Acceptance Evidence`, `## Provenance`), not `## Status`. The
lifecycle gate compares any `## Status` section against the frontmatter enum and
requires the section to open with the enum word, so a section named Status is
obliged to restate the enum. Naming it for its contents avoids that entirely.
-->

## Context

[Describe the problem, forces at play, and why a decision is needed. Be specific about what is driving this decision.]

## Decision

[State the decision that was made. Be clear and unambiguous.]

## Prior Art Investigation (Required when changing existing systems)

Complete this section when the ADR proposes changes to existing patterns, constraints, or architecture.
Use `python3 .claude/skills/chestertons-fence/scripts/investigate.py` to automate research.

### What Currently Exists

- **Structure/pattern being changed**: [Describe what exists today]
- **When introduced**: [PR/ADR reference, commit, date]
- **Original author and context**: [Who created it and why]

### Historical Rationale

- **Why was it built this way?** [Original problem it solved]
- **What alternatives were considered?** [Prior trade-off analysis]
- **What constraints drove the design?** [Technical or organizational factors]

### Why Change Now

- **Has the original problem changed?** [Yes/No, evidence]
- **Is there a better solution now?** [Yes/No, what changed]
- **What are the risks of change?** [Blast radius, migration cost]

## Rationale

[Explain why this decision was made. Include:]

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| [Option 1] | [Pros] | [Cons] | [Reason] |
| [Option 2] | [Pros] | [Cons] | [Reason] |

### Trade-offs

[Discuss the trade-offs involved in this decision]

## Consequences

### Positive

- [Positive consequence 1]
- [Positive consequence 2]

### Negative

- [Negative consequence 1]
- [Negative consequence 2]

### Neutral

- [Neutral consequence 1]

## Impact on Dependent Components

[Required when changing canonical source files (e.g., SESSION-PROTOCOL.md). List all components that depend on the changed file and describe the required updates.]

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| [e.g., Session log templates] | [Direct/Indirect] | [What must change] | [Low/Medium/High] |
| [e.g., Validation scripts] | [Direct/Indirect] | [What must change] | [Low/Medium/High] |
| [e.g., CI workflows] | [Direct/Indirect] | [What must change] | [Low/Medium/High] |

## Implementation Notes

[Optional: Add any implementation details, steps, or guidelines]

## Related Decisions

- [Link to related ADRs]

## References

- [External references, documentation, or standards]

---

## Agent-Specific Fields (Required for Agent ADRs)

### Agent Name

[Name of the proposed/changed agent]

### Overlap Analysis

| Existing Agent | Capability Overlap | Overlap % | Differentiation |
|----------------|-------------------|-----------|-----------------|
| [Agent name] | [Overlapping capabilities] | [%] | [How this agent differs] |

### Entry Criteria

| Scenario | Priority | Confidence |
|----------|----------|------------|
| [When to use] | P0/P1/P2 | High/Med/Low |

### Explicit Limitations

1. [What this agent CANNOT do]
2. [What this agent should NOT be used for]

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| [Metric] | [Target] | [How to measure] |

---

*Template Version: 1.1*
*Created: 2025-12-13*
*GitHub Issue: #8*
