# Architectural Decision Records (ADR) - Foundational Concepts

**Source**: User-provided definition (2025-12-23)
**Category**: Architectural Knowledge Management (AKM)

## Core Definitions

### Architectural Decision (AD)

A **justified design choice** that addresses a functional or non-functional requirement that is architecturally significant.

**Key characteristics**:
- Must be justified (has rationale)
- Addresses specific requirements (functional or non-functional)
- Architecturally significant (has measurable impact)

### Architecturally Significant Requirement (ASR)

A requirement that has a **measurable effect** on the architecture and quality of a software and/or hardware system.

**Significance criteria**:
- Measurable impact on architecture
- Affects system quality attributes
- Influences structural design decisions

### Architectural Decision Record (ADR)

Captures a **single AD and its rationale**.

**Purpose**: Help understand:
- Reasons for a chosen architectural decision
- Trade-offs considered
- Consequences (positive and negative)

**Value proposition**: Prevents "why did we do this?" questions by documenting context and reasoning at decision time.

### Decision Log

The **collection of ADRs** created and maintained in a project.

**Characteristics**:
- Living documentation
- Chronological record of architectural evolution
- Provides historical context for current architecture

### Architectural Knowledge Management (AKM)

The broader discipline that encompasses:
- Architectural decisions
- Decision rationale
- Trade-off analysis
- Consequence tracking
- Knowledge preservation

**Scope**: All aspects of managing architectural knowledge over a project's lifecycle.

## Extended Usage: The "Any Decision Record" Debate

**Source**: [ADR = Any Decision Record? Architecture, Design and Beyond](https://ozimmer.ch/practices/2021/04/23/AnyDecisionRecords.html), [MADR](https://adr.github.io/madr/)

### The Broadening Movement

**MADR** now stands for "Markdown **Any** Decision Records" (not "Architectural")

**Rationale for expansion**:
- Many design decisions that don't qualify as architecturally significant are still worth capturing
- Autonomous teams make managerial and organizational decisions that benefit from ADR format
- Strategy decisions, tooling choices, and process decisions all require justification and trade-off analysis

**Extended usage includes**:
- Design decisions (not just architecture)
- Process decisions
- Tool selection decisions
- Governance policies
- Managerial and organizational decisions

### The Counterargument: Maintain Focus

**Concern**: Broadening ADRs dilutes their architectural focus

**Arguments against "Any Decision Record"**:
- Mixing architectural and non-architectural decisions obscures architectural evolution
- Lacks specificity - turns ADR into a catch-all for "any significant decision"
- Better to create **separate records** for architectural vs other important decisions
- ADRs should focus on decisions affecting system structure, non-functional characteristics, dependencies, interfaces, or construction techniques

**Recommendation from critics**: "ADRs are not Any Decision Records" - keep architectural decisions separate from operational/process decisions

### Resolution in This Codebase

**Hybrid approach**:
- **`.agents/architecture/`** - Architectural Decision Records (strict ADR definition)
- **`.agents/governance/`** - Governance policies and operational decisions

**Example**: 
- `ADR-014` (in architecture) defines runner selection decision and rationale
- `COST-GOVERNANCE.md` (in governance) operationalizes the policy with compliance requirements

**When to use which**:
- Use ADR for decisions affecting system structure, quality attributes, or technical architecture
- Use governance docs for operational policies, compliance requirements, and process standards

**Generalization**: The ADR pattern is valuable for any significant decision requiring:
- Justification
- Trade-off analysis
- Long-term understanding
- Reversibility (if consequences prove undesirable)

## Relationships

```text
AKM (Architectural Knowledge Management)
  └─ Decision Log (collection of ADRs)
      └─ ADR (Architectural Decision Record)
          └─ AD (Architectural Decision)
              └─ ASR (Architecturally Significant Requirement)
```

## Practical Application in This Codebase

**Current ADR catalog**: `.agents/architecture/ADR-*.md`

**Examples**:
- ADR-017: Model routing policy (addresses quality requirement: false PASS rate)
- ADR-014: Distributed handoff architecture (addresses scalability requirement: merge conflicts)
- ADR-010: Quality gates (addresses reliability requirement: consistent review verdicts)

**Decision process**: Multi-agent debate protocol (Sessions 86-90) validates ADRs before acceptance.

## Key Insight

An ADR is NOT just documentation—it's a **decision artifact** that:
1. Forces explicit reasoning at decision time
2. Preserves context for future maintainers
3. Enables reversibility (if consequences prove undesirable)
4. Supports learning (what worked, what didn't)

## Related Memories

- `skill-debate-001-multi-agent-adr-consensus`: Process for validating ADRs
- `skills-architecture`: Architectural skills and patterns
- `adr-014-review-findings`: Example of ADR review process

## References

- Wikipedia: [Architectural Decision](https://en.wikipedia.org/wiki/Architectural_decision)
- Wikipedia: [Architecturally Significant Requirements](https://en.wikipedia.org/wiki/Architecturally_significant_requirements)
- This codebase: `.agents/architecture/` directory
