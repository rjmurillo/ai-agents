# ADR-049: ADR Exception Criteria (Chesterton's Fence)

## Status

Proposed

## Date

2026-02-19

## Context

ADRs codify architectural decisions. Sometimes legitimate exceptions arise. The exception process should balance flexibility with discipline.

PR #908 created an exception to ADR-005 (PowerShell-only scripting) for Python hooks without documenting:

1. Why ADR-005 existed (its original purpose)
2. Alternatives attempted before requesting exception
3. Impact of creating the exception

The exception was approved based on immediate need (Anthropic SDK only available in Python). This expedient choice bypassed the architectural reasoning that ADR-005 encoded.

G.K. Chesterton's fence principle applies: do not remove a fence until you understand why it was built. Similarly, do not create ADR exceptions until you understand why the rule exists.

### Problem Statement

Creating ADR exceptions is too easy. The current process:

1. Identify constraint blocking implementation
2. Request exception in PR
3. Document scope and conditions

This process misses critical analysis:

- Why does the ADR exist? What problem did it solve?
- What happens if we weaken the rule? What debt accumulates?
- Did we try to comply before requesting exception?

### Observed Symptoms

| Symptom | Evidence |
|---------|----------|
| Exception without rationale | ADR-005 Python exception cites SDK availability, not why PowerShell rule existed |
| Missing alternatives | PR #908 did not document attempts at PowerShell HTTP calls to Anthropic API |
| Scope creep | Exception for "hooks with LLM integration" became pattern for all Python hooks |
| Lost institutional knowledge | Future maintainers see exception, not original constraint |

## Decision

ADR exceptions require documented Chesterton's Fence analysis before approval.

### Required Analysis

Every ADR exception request MUST document:

| Element | Question | Purpose |
|---------|----------|---------|
| **Original Rationale** | Why does this ADR exist? | Prove understanding of the rule |
| **Impact Assessment** | What breaks if we weaken this rule? | Surface hidden costs |
| **Compliance Attempts** | What alternatives did we try first? | Verify exception is necessary |
| **Scope Containment** | How do we prevent this exception from becoming the norm? | Limit precedent |

### Exception Request Template

```markdown
## Exception Request: [ADR-NNN]

### 1. Original Rationale
[Why does ADR-NNN exist? Quote relevant sections.]

### 2. Compliance Attempts
| Approach | Result | Why Insufficient |
|----------|--------|------------------|
| [Attempt 1] | [Outcome] | [Reason] |
| [Attempt 2] | [Outcome] | [Reason] |

### 3. Impact Assessment
- **Rule weakened how**: [Description]
- **Technical debt introduced**: [Description]
- **Precedent risk**: [How others might cite this exception]

### 4. Scope Containment
- **Exact scope**: [File paths, conditions]
- **Expiration**: [Sunset condition or review date]
- **Enforcement**: [How compliance will be verified]

### 5. Decision
[Accept/Reject with summary]
```

### Review Process

1. Exception requests trigger mandatory architect agent review
2. Architect verifies all four elements are documented
3. Incomplete analysis blocks exception approval
4. Approved exceptions are documented in the ADR's Exceptions section

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (informal exceptions) | Fast, low friction | Loses rationale, enables shortcuts | PR #908 demonstrates failure mode |
| Blanket prohibition (no exceptions) | Maximum enforcement | Inflexible, blocks legitimate needs | Exceptions exist for good reasons |
| Architect approval only (no docs) | Adds oversight | Rationale lost after approval | Same problem as status quo |
| Automated enforcement | Consistent | Cannot evaluate architectural judgment | Exceptions require human review |

### Trade-offs

**Friction vs Integrity**: This process adds 10-15 minutes to exception requests. This friction is intentional. If an exception is not worth 15 minutes of analysis, it is not worth the architectural debt it creates.

**Documentation vs Speed**: Complete analysis takes longer than "just approve it." The analysis serves future maintainers who will encounter the exception without original context.

## Consequences

### Positive

- Exceptions documented with full context
- Future maintainers understand trade-offs
- Reduces tactical violations disguised as exceptions
- Forces compliance attempts before exceptions
- Preserves ADR authority

### Negative

- Slows exception approval process (intentional)
- Requires more upfront documentation
- May be perceived as bureaucratic

### Neutral

- Does not prevent legitimate exceptions
- Analysis effort proportional to exception significance

## Implementation Notes

### Enforcement

The architect agent template includes:

```markdown
## ADR Exception Review Checklist

Before approving any ADR exception:

- [ ] Original rationale documented (quotes from ADR)
- [ ] At least one compliance attempt documented
- [ ] Impact assessment complete
- [ ] Scope containment defined
- [ ] Expiration or review date set
```

### Retroactive Application

Existing exceptions (e.g., ADR-005 Python exceptions) do not require retroactive analysis. This ADR applies to future exception requests only.

### Metrics

Track exception approval rate before/after this ADR:

- Baseline: Exceptions approved / exceptions requested
- Target: 80% of requests include complete analysis within 90 days

## Related Decisions

- ADR-005: PowerShell-Only Scripting Standard (example of exception without analysis)
- ADR-042: Python Migration Strategy (superseded ADR-005)
- ADR-033: Routing Level Enforcement Gates (gates prevent bypass)

## References

- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (lines 1341-1347)
- Issue #938 (criteria document)
- Issue #947 (this ADR)
- [Chesterton's Fence](https://en.wikipedia.org/wiki/G._K._Chesterton#Chesterton's_fence) (principle)

---

*Template Version: 1.0*
*Created: 2026-02-19*
*GitHub Issue: #947*
