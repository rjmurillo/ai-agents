---
status: NEEDS_CHANGES              # APPROVED | NEEDS_CHANGES | BLOCKED
priority: P1                       # P0 | P1 | P2 (severity if not approved)
blocking: true                     # true = CI blocks merge, false = advisory
reviewer: architect                # agent performing review
date: YYYY-MM-DD                   # review date (ISO 8601)
pr-branch: feature/example         # (optional) git branch being reviewed
scope: "[Review scope]"            # (optional) brief description of review scope
---

# Design Review: [Title]

## Executive Summary

**Verdict**: [APPROVED | NEEDS_CHANGES | BLOCKED]

[1-3 sentence summary of the review outcome.]

## Context

[What is being reviewed. Include PR number, issue number, and scope.]

## Architectural Assessment

### ADR Compliance

| ADR | Status | Evidence |
|-----|--------|----------|
| [ADR-NNN] | COMPLIANT / VIOLATION | [Brief evidence] |

### Pattern Consistency

| Pattern | Compliance | Evidence |
|---------|-----------|----------|
| [Pattern name] | PASS / FAIL | [Brief evidence] |

## Findings

### Blocking (if any)

1. **[Finding title]**: [Description of the blocking issue and required resolution]

### Non-Blocking (if any)

1. **[Finding title]**: [Description and recommendation]

## Recommendations

[Ordered list of actions for the author.]

## Verification Checklist

- [ ] Problem statement is clear
- [ ] Solution aligns with existing architecture
- [ ] ADR compliance verified
- [ ] Test coverage adequate
- [ ] No breaking changes (or migration documented)
- [ ] Security considerations addressed

---

**Review Date**: YYYY-MM-DD
**Review Duration**: [Approximate time]
**Artifacts Reviewed**: [Count and types]
