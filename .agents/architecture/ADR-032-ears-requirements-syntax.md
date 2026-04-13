# ADR-032: EARS Requirements Syntax Standard

## Status

Accepted

## Date

2025-12-30

## Context

The ai-agents project is implementing a specification layer (Phase 1: Spec Layer per Issue #193) to formalize requirements, improve traceability, and enable automated validation. Traditional natural language requirements suffer from well-documented problems:

**Ambiguity**: Requirements like "the system should be fast" or "handle errors gracefully" are open to interpretation. Different agents, reviewers, and implementations may understand them differently.

**Untestability**: Without measurable criteria, requirements cannot be objectively verified. "Appropriate response time" provides no acceptance criteria.

**Unclear Triggers**: Requirements often omit when they apply. "Validate input" doesn't specify which events trigger validation.

**Inconsistent Format**: Ad-hoc requirement writing leads to varying quality and structure, making automated processing difficult.

The project needs a standardized syntax for requirements that:

1. Enforces testable, unambiguous language
2. Supports automated parsing and validation
3. Integrates with the existing critic agent workflow
4. Aligns with industry-recognized practices

## Decision

Adopt the EARS (Easy Approach to Requirements Syntax) format as the standard for all formal requirements in the ai-agents project.

EARS provides six patterns covering different requirement types:

| Pattern | Syntax | Use Case |
|---------|--------|----------|
| **Ubiquitous** | THE SYSTEM SHALL [action] | Always-active constraints |
| **Event-driven** | WHEN [trigger] THE SYSTEM SHALL [action] | Triggered behaviors |
| **State-driven** | WHILE [condition] THE SYSTEM SHALL [action] | Condition-dependent behaviors |
| **Optional** | WHERE [feature enabled] THE SYSTEM SHALL [action] | Configurable features |
| **Unwanted** | IF [condition] THEN THE SYSTEM SHALL [prevent] | Negative requirements |
| **Complex** | WHEN [trigger] AND [condition] ... UNLESS [exception] | Combined conditions |

All requirements MUST include a "SO THAT [rationale]" clause to document business value.

## Rationale

### Why EARS Specifically

EARS was developed by Alistair Mavin et al. at Rolls-Royce and has been validated through industrial application in safety-critical systems. It balances rigor with simplicity:

- **Proven Track Record**: Used in aerospace, automotive, and defense industries
- **Teachable**: Minimal training required compared to formal methods
- **Tool-Friendly**: Regular structure enables automated parsing
- **Complete Coverage**: Six patterns cover all common requirement types

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Gherkin (Given-When-Then)** | Familiar to BDD practitioners, executable specs | Test-focused, not requirements-focused; verbose | Conflates requirements with test scenarios; doesn't distinguish ubiquitous vs triggered |
| **RFC 2119 Keywords** | Industry standard (MUST, SHALL, etc.) | No structure for triggers/conditions; ambiguity remains | Already use RFC 2119 keywords; EARS adds the structural layer on top |
| **Formal Methods (Z, Alloy)** | Mathematically precise | Steep learning curve; overkill for this project | Agent developers can't reasonably write/review formal specs |
| **Natural Language with Templates** | Flexible | Inconsistent quality; still ambiguous | Previous approach that led to current problems |
| **User Stories (As a... I want... So that...)** | User-centric | Implementation-agnostic; doesn't specify system behavior | Better for capturing needs, not specifying behavior |

### Trade-offs

**Pros**:

- Eliminates ambiguity through constrained syntax
- Enables critic agent to validate requirements automatically
- Provides clear acceptance criteria for QA
- Maintains traceability (SO THAT clause documents rationale)

**Cons**:

- Requires writers to learn EARS patterns
- More verbose than informal requirements
- May feel bureaucratic for simple features
- Not all requirements fit neatly into patterns

## Consequences

### Positive

- **Testability**: Every requirement has verifiable acceptance criteria
- **Consistency**: All requirements follow the same structure
- **Automation**: Critic agent can validate EARS syntax compliance
- **Traceability**: SO THAT clause links requirements to business value
- **Reduced Rework**: Ambiguities caught early in spec phase, not implementation

### Negative

- **Learning Curve**: Contributors must learn EARS patterns (mitigated by examples)
- **Overhead**: Writing formal requirements takes longer than informal notes
- **Over-Specification Risk**: May encourage specifying implementation details

### Neutral

- Existing informal requirements in session logs remain valid as working notes
- EARS applies to formal specification documents, not all documentation
- Integration with existing memory and session systems requires coordination

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| EARS adoption rate | 0% | 100% of new specs | Audit `.agents/specs/requirements/` |
| First-submission pass rate | N/A | >80% pass critic validation | Track critic feedback per spec |
| Vague term usage | Unmeasured | 0 instances in approved specs | Grep for banned terms |
| Spec-to-implementation rework | Unmeasured | <20% revision rate | Track PR revision counts |

**Evaluation**: Assess after 10 formal requirements. If revision rate exceeds 50% due to EARS awkwardness, revisit format selection.

## Rollback Strategy

**Exit criteria**: EARS patterns prove insufficient OR overhead exceeds benefit.

**Rollback path**: Revert to natural language requirements. No migration required—delete template and write informal prose. Lock-in level: **None** (EARS is a syntax convention, not infrastructure).

## Implementation Notes

### Required Artifacts

1. **EARS Format Template**: `.agents/governance/ears-format.md` (already created in PR #603)
2. **Critic Agent Update**: Add EARS validation checklist to critic prompt
3. **Example Requirements**: Create sample specs demonstrating each pattern

### YAML Front Matter Schema

All EARS requirement documents include structured metadata:

```yaml
---
type: requirement
id: REQ-NNN
title: Short descriptive title
status: draft | review | approved | implemented
priority: P0 | P1 | P2
category: functional | non-functional | constraint
related:
  - REQ-000  # Related requirements
  - ADR-NNN  # Supporting decisions
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### Validation Checklist (for Critic Agent)

- [ ] Uses correct EARS pattern syntax
- [ ] Has complete YAML front matter
- [ ] Contains measurable/testable criteria
- [ ] Avoids vague terminology ("appropriate", "reasonable")
- [ ] Links to related artifacts (ADRs, parent requirements)
- [ ] Single requirement per document (atomic)

### Applicability Scope

EARS applies to:

- Formal requirement specifications in `.agents/specs/`
- Design documents referencing system behaviors
- PRDs and planning documents with behavioral requirements

EARS does NOT apply to:

- Session logs (working notes, not formal specs)
- Code comments
- Informal discussions or brainstorming
- User-facing documentation

## Related Decisions

- [ADR-005: PowerShell-Only Scripting Standard](ADR-005-powershell-only.md) - Referenced as example constraint requirement
- [ADR-010: Quality Gates with Evaluator-Optimizer](ADR-010-quality-gates-evaluator-optimizer.md) - Critic agent integration
- [ADR-017: Tiered Memory Index Architecture](ADR-017-memory-index-architecture.md) - Requirements link to memory system

## References

- Mavin, A., Wilkinson, P., Harwood, A., & Novak, M. (2009). "Easy Approach to Requirements Syntax (EARS)". IEEE International Requirements Engineering Conference.
- [EARS Format Template](./../governance/ears-format.md) - Project implementation
- [Issue #595](https://github.com/rjmurillo/ai-agents/issues/595) - S-001: Create EARS format template
- [Issue #193](https://github.com/rjmurillo/ai-agents/issues/193) - Phase 1: Spec Layer Implementation

---

*ADR Version: 1.0*
*Created: 2025-12-30*
*Author: Claude (architect agent)*
