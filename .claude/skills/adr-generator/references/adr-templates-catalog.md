# ADR Templates Catalog

Reference catalog of well-known ADR template formats. Choose a template based on the decision's complexity and team needs. This project's [canonical template](../../.agents/architecture/ADR-TEMPLATE.md) is the default.

## Template Comparison

| Template | Complexity | Best For | Key Feature |
|----------|-----------|----------|-------------|
| **Project Canonical** | High | This project (default) | Prior Art Investigation, coded consequences, agent fields |
| **MADR** | Medium-High | Formal evaluation of alternatives | Decision drivers, per-option pros/cons |
| **Nygard** | Low | Fast-paced teams, simple decisions | Minimal: Context, Decision, Consequences |
| **Y-Statement** | Minimal | Quick capture, one-sentence decisions | Single structured sentence |
| **Alexandrian** | Low-Medium | Pattern-oriented teams | Prologue/Discussion/Solution/Consequences |
| **Tyree & Akerman** | High | Enterprise, regulated environments | Assumptions, constraints, implications, traceability |
| **Planguage** | Medium | Quality/metrics-oriented decisions | Stakeholders, risks, assumptions as first-class fields |
| **EdgeX** | Medium | IoT/edge computing projects | Structured for distributed systems |
| **arc42** | Medium | Teams using arc42 documentation | Integrates with arc42 architecture framework |
| **Business Case** | High | MBA-oriented, cost-driven decisions | SWOT analysis, cost/benefit, ROI |
| **Paulo Merson** | Medium | Academic/research teams | Explicit decision drivers and confirmation |

---

## Project Canonical Template (Default)

The project's standard template at `.agents/architecture/ADR-TEMPLATE.md`. Use this unless the user requests a different format.

**Sections**: Status, Date, Context, Decision, Prior Art Investigation (conditional), Rationale (with Alternatives table and Trade-offs), Consequences (Positive/Negative/Neutral), Impact on Dependent Components (conditional), Implementation Notes, Related Decisions, References, Agent-Specific Fields (conditional).

See [adr-template.md](adr-template.md) for the full template.

---

## MADR (Markdown Architectural Decision Records)

Source: [github.com/adr/madr](https://github.com/adr/madr) (CC0-1.0 license)

```markdown
---
status: "{proposed | rejected | accepted | deprecated | superseded by ADR-0123}"
date: {YYYY-MM-DD when the decision was last updated}
decision-makers: {list everyone involved in the decision}
---

# {short title, representative of solved problem and found solution}

## Context and Problem Statement

{Describe the context and problem statement, e.g., in free form using
two to three sentences or in the form of an illustrative story.}

## Decision Drivers

* {decision driver 1, e.g., a desired software quality, faced concern, constraint}
* {decision driver 2}

## Considered Options

* {title of option 1}
* {title of option 2}
* {title of option 3}

## Decision Outcome

Chosen option: "{title of option 1}", because {justification}.

### Consequences

* Good, because {positive consequence}
* Bad, because {negative consequence}

### Confirmation

{Describe how the implementation/compliance of the ADR can be confirmed.}

## Pros and Cons of the Options

### {title of option 1}

* Good, because {argument a}
* Neutral, because {argument b}
* Bad, because {argument c}

### {title of option 2}

* Good, because {argument a}
* Bad, because {argument b}

## More Information

{Additional evidence, team agreement, links to other decisions.}
```

---

## Nygard Template

Source: [Michael Nygard, "Documenting Architecture Decisions" (2011)](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions)

The original and most widely adopted ADR format. Minimal by design.

```markdown
# {Title}

## Status

{proposed | accepted | rejected | deprecated | superseded}

## Context

What is the issue that we're seeing that is motivating this decision or change?

## Decision

What is the change that we're proposing and/or doing?

## Consequences

What becomes easier or more difficult to do because of this change?
```

---

## Y-Statement Template

An ultra-minimal single-sentence format:

```text
In the context of {use case/user story},
facing {concern},
we decided for {option}
to achieve {quality},
accepting {downside}.
```

Use when: a decision needs quick capture with minimal ceremony. Can be extended with additional rationale and status.

---

## Alexandrian Pattern Template

Inspired by Christopher Alexander's pattern language.

```markdown
# {Title}

## Prologue (Summary)

In the context of {use case},
facing {concern},
we decided for {option}
to achieve {quality},
accepting {downside}.

## Discussion (Context)

Explains the forces at play (technical, political, social, project).
This is the story explaining the problem we are looking to resolve.

## Solution

Explains how the decision will solve the problem.

## Consequences

Explains the results of the decision over the long term.
Did it work, not work, was changed, upgraded, etc.
```

---

## Tyree & Akerman Template

Source: ["Architecture Decisions: Demystifying Architecture" by Jeff Tyree and Art Akerman](https://www.utdallas.edu/~chung/SA/zz-Impreso-architecture_decisions-tyree-05.pdf)

Comprehensive format for enterprise and regulated environments.

**Fields**: Issue, Decision, Status, Group, Assumptions, Constraints, Positions, Argument, Implications, Related decisions, Related requirements, Related artifacts, Related principles, Notes.

---

## Planguage Template

A planning-language approach with quality and metrics focus.

**Fields**: Tag, Gist, Requirement, Rationale, Priority, Stakeholders, Status, Owner, Author, Revision, Date, Assumptions, Risks, Defined.

Source: [Planguage specification by Tom Gilb](https://www.iaria.org/conferences2012/filesICCGI12/Tutorial%20Specifying%20Effective%20Non-func.pdf)

---

## References

- [ADR Templates Catalog](https://adr.github.io/adr-templates/)
- [MADR Repository](https://github.com/adr/madr)
- [Joel Parker Henderson ADR Collection](https://github.com/joelparkerhenderson/architecture-decision-record)
- [ISO/IEC/IEEE 42010:2011](https://en.wikipedia.org/wiki/ISO/IEC_42010) — International standard for architecture descriptions
