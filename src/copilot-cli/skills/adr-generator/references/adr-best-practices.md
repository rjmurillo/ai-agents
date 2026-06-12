# ADR Best Practices

Writing guidance adapted from [Joel Parker Henderson's ADR collection](https://github.com/joelparkerhenderson/architecture-decision-record) and community best practices.

## Characteristics of a Good ADR

- **Rationale**: Explain the reasons for the decision. Include context, pros and cons, feature comparisons, cost/benefit discussions.
- **Specific**: Each ADR addresses one decision, not multiple.
- **Timestamped**: Identify when each item is written. Important for aspects that change over time (costs, schedules, scaling).
- **Mutable by a decidable rule**: Whether you may edit an accepted ADR depends on whether it has been implemented. See [ADR Mutability and Superseding](#adr-mutability-and-superseding) for the exact rule. Short version: clarifications and consequences are editable in place (update `date`); a decision change after any implementation requires a new superseding ADR.

## Writing Good Context Sections

- Explain the organization's situation and business priorities
- Include rationale based on social and skills makeups of teams
- Include pros and cons described in terms that align with needs and goals
- Describe the problem, not the solution

## Writing Good Consequences Sections

- Explain what follows from making the decision: effects, outcomes, outputs, follow-ups
- Include information about subsequent ADRs triggered by this decision
- Include after-action review processes (teams typically review each ADR one month later)

## ADR Mutability and Superseding

The field splits three ways on whether an accepted ADR may be edited:

| School | Rule | Source |
|--------|------|--------|
| Strict append-only | Accepted (and rejected) ADRs are immutable; any change is a new superseding ADR; only the old ADR's status field changes. | AWS Prescriptive Guidance; Azure Well-Architected ("append-only log; don't edit accepted records") |
| No rule | Nygard never says "immutable"; MADR's `date` means "when the decision was last updated" and all fields are optional. | Nygard 2011; MADR 4.0.0 |
| Bounded in-place edits | Clarifications editable any time; Consequences updatable during implementation; replace in place only if never implemented and stakeholders agree; once any implementation occurred, supersede. | GDS Way |

This project adopts the **GDS Way bounded rule**, because it is the only published rule with an objective boundary (implementation status):

1. **Clarifications**: edit in place, update `date`.
2. **Consequences**: update in place as implementation teaches, update `date`.
3. **Decision change before any implementation**: replace in place with stakeholder agreement, update `date`.
4. **Decision change after any implementation**: create a new superseding ADR. Never delete the old one.

An `implemented` boolean that flips at the first merged change gives this rule an objective, git-checkable gate between cases 3 and 4.

When a new ADR supersedes another:

- Create the new ADR (do not rewrite the old one's decision).
- Set the old ADR's status to `superseded` and reference the replacement (`Superseded by ADR-NNN`).
- Reference the old ADR from the new one.

Keep superseded ADRs; never delete them. This retention rule is unanimous across all sources.

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
- Treat ADRs as living documents only within the bounded rule above: clarifications and pre-implementation changes edit in place; post-implementation decision changes supersede. Always date each change
- Typical updates: new teammates, new offerings, real-world results, vendor changes

## References

- [Joel Parker Henderson ADR Collection](https://github.com/joelparkerhenderson/architecture-decision-record)
- [Michael Nygard, "Documenting Architecture Decisions" (2011)](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR Templates Catalog](https://adr.github.io/adr-templates/)
- [Arc42](https://arc42.org/): architecture documentation framework
- [C4 Model](https://c4model.com/): architecture diagramming approach
