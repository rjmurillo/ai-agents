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
