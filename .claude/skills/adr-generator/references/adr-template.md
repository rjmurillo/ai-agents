# ADR Template

This project's canonical ADR template. Source: `.agents/architecture/ADR-TEMPLATE.md`.

During Phase G2 (Research), the skill detects which template is in use at the destination. This template is the default for this project. For other template formats, see [adr-templates-catalog.md](adr-templates-catalog.md).

---

```markdown
# ADR-NNN: [Title]

## Status

[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Date

[YYYY-MM-DD]

## Context

[Describe the problem, forces at play, and why a decision is needed.
Be specific about what is driving this decision.]

## Decision

[State the decision that was made. Be clear and unambiguous.]

## Prior Art Investigation (Required when changing existing systems)

Complete this section when the ADR proposes changes to existing patterns,
constraints, or architecture.

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

[Explain why this decision was made.]

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

[Required when changing canonical source files. List all components that
depend on the changed file and describe the required updates.]

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| [e.g., Session log templates] | [Direct/Indirect] | [What must change] | [Low/Medium/High] |

## Implementation Notes

[Optional: Add any implementation details, steps, or guidelines]

## Related Decisions

- [Link to related ADRs]

## References

- [External references, documentation, or standards]
```

## Agent-Specific Fields (Conditional)

Include these additional sections only when the ADR is about an agent:

```markdown
## Agent-Specific Fields

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
```
