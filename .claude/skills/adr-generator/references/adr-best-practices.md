# ADR Best Practices

Writing guidance adapted from [Joel Parker Henderson's ADR collection](https://github.com/joelparkerhenderson/architecture-decision-record) and community best practices.

## Characteristics of a Good ADR

- **Rationale**: Explain the reasons for the decision. Include context, pros and cons, feature comparisons, cost/benefit discussions.
- **Specific**: Each ADR addresses one decision, not multiple.
- **Timestamped**: Identify when each item is written. Important for aspects that change over time (costs, schedules, scaling).
- **Immutable**: Do not alter existing information in a finalized ADR. Instead, amend with dated additions or supersede by creating a new ADR. In practice, teams often treat ADRs as living documents with dated amendments — this is acceptable provided each change includes a date stamp and preserves the original reasoning.

## Writing Good Context Sections

- Explain the organization's situation and business priorities
- Include rationale based on social and skills makeups of teams
- Include pros and cons described in terms that align with needs and goals
- Describe the problem, not the solution

## Writing Good Consequences Sections

- Explain what follows from making the decision: effects, outcomes, outputs, follow-ups
- Include information about subsequent ADRs triggered by this decision
- Include after-action review processes (teams typically review each ADR one month later)

## Superseding ADRs

When an AD replaces or invalidates a previous ADR:

- Create a new ADR (do not modify the old one)
- Mark the old ADR as `Superseded by ADR-NNN`
- Reference the old ADR in the new one

## File Naming Approaches

Different projects use different conventions. Detect from existing files.

| Convention | Example | Common In |
|-----------|---------|-----------|
| Number-prefixed uppercase | `ADR-042-database-selection.md` | Enterprise, governance-heavy |
| Number-prefixed lowercase | `0042-database-selection.md` | adr-tools, MADR |
| Verb-phrase (no number) | `choose-database.md` | Lightweight teams |
| Numbered with title | `adr-042-database-selection.md` | Mixed environments |

Present-tense imperative verb phrases aid readability: `choose-database`, `format-timestamps`, `handle-exceptions`.

## ADR Lifecycle

ADRs progress through stages:

| Stage | Description |
|-------|-------------|
| **Proposed** | Initial draft, open for discussion |
| **Accepted** | Decision approved by stakeholders |
| **Deprecated** | Decision no longer relevant but kept for history |
| **Superseded** | Replaced by a newer ADR |
| **Rejected** | Decision was considered but not adopted |

## When to Write an ADR

Write an ADR when:

- Future developers need to understand the "why" behind a choice
- The decision affects multiple components or teams
- The decision involves significant trade-offs
- The choice is not obvious from the code alone

Skip an ADR when:

- The decision is limited in scope, time, risk, and cost
- The decision is already covered by standards, policies, or documentation
- The decision is temporary (workarounds, proofs of concept, experiments)

## Teamwork

- Talk about the "why", do not mandate the "what"
- Some teams prefer the directory name "decisions" over the abbreviation "ADRs"
- In practice, teams treat ADRs as living documents with dated amendments rather than strict immutability — this works well when each change includes a date stamp
- Typical updates: new teammates, new offerings, real-world results, vendor changes

## References

- [Joel Parker Henderson ADR Collection](https://github.com/joelparkerhenderson/architecture-decision-record)
- [Michael Nygard, "Documenting Architecture Decisions" (2011)](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR Templates Catalog](https://adr.github.io/adr-templates/)
- [Arc42](https://arc42.org/) — Architecture documentation framework
- [C4 Model](https://c4model.com/) — Architecture diagramming approach
