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
The frontmatter above is authoritative for tooling (ADR-073). This template
carried `## Status` and `## Date` prose sections until 2026-08-21 as *required*
scaffolding; both restated frontmatter fields verbatim, and every record
generated from it inherited the duplication with nothing added. Two review
comments on PR #5209 (ADR-005 "Duplicative. Already in frontmatter", ADR-024
"Redundant") rejected that. They are no longer pre-filled here.

The rule: prose says what frontmatter cannot, and never restates it alone.

`## Status` remains available and is NOT discouraged. ADR-073 retains it as the
human-readable secondary rendering, and says it "may carry the nuance the enum
cannot": a review verdict, the condition still blocking acceptance, the
conditional state ADR-072 uses. Include it whenever you have such nuance. When
you do, open it with the enum word, because the lifecycle gate reconciles the
two and frontmatter wins on disagreement; "Accepted. Conditional on X shipping."
satisfies both the gate and the reader.

Omit it when you have nothing the enum does not already say. A section reading
only "Superseded by ADR-042" beside `superseded-by: ADR-042` is drift surface,
not a service to the reader. Omitting it is not a violation: the gate treats a
missing prose status as fine, because ADR-073 says "may", not "must".

Where the nuance is not about lifecycle at all, name the section for what it
holds (`## Acceptance Evidence`, `## Provenance`) so no reader mistakes it for a
second source of truth about state.
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
