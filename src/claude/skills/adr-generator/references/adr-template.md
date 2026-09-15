# ADR Template

This project's canonical ADR template. Source: `.agents/architecture/ADR-TEMPLATE.md`.

During Phase G2 (Research), the skill detects which template is in use at the destination. This template is the default for this project. For other template formats, see [adr-templates-catalog.md](adr-templates-catalog.md).

---

```markdown
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

## `review-by` Frontmatter Field (Optional)

Set `review-by` when the ADR's prose commits to a revisit date: a provisional
window, a trial period, a re-review checkpoint, a sunset date. Use `null`
(the default) when the decision carries no deadline, including when the revisit
is condition-triggered rather than calendar-triggered.

| Value | Meaning |
|-------|---------|
| `null` | No calendar deadline. The default. |
| `YYYY-MM-DD` | The date by which this record must be revisited. |

The field is optional and unenforced, matching the `explainer` and `implemented`
precedent in ADR-073 Phase 1. It records the deadline the prose already states;
it does not create one. Whichever section states the deadline stays authoritative
prose, and the date here must match it.

## Coded Consequences Convention (Optional)

The Project Canonical format supports coded bullets so multi-item sections can be
referenced precisely from review threads and other ADRs. Folded from the former
`adr-generator` agent (Issue #2104). Use a 3-letter code plus a zero-padded
3-digit number, incrementing within each section. ADR-039 is a live example.

| Section | Code prefix | Example |
|---------|-------------|---------|
| Positive consequences | `POS-` | `- **POS-001**: cuts cold start from 4.2s to 0.6s` |
| Negative consequences | `NEG-` | `- **NEG-001**: adds a second store to operate` |
| Alternatives | `ALT-` | `- **ALT-001**: **Description**: ... **Rejection Reason**: ...` |
| Implementation notes | `IMP-` | `- **IMP-001**: migrate readers before dropping the field` |
| References | `REF-` | `- **REF-001**: ADR-035 exit-code standardization` |

Increment `ALT-` codes across all alternatives, not per alternative. Reserve the
codes for sections with two or more items; a single-item section does not need
them.

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

<!-- vendor-portability: declared. This bundled template names .agents/architecture/ADR-TEMPLATE.md as the project's canonical source it mirrors. The bundled copy is self-contained; a vendored install uses this file directly and the canonical path is provenance only. Issue #2050. -->
