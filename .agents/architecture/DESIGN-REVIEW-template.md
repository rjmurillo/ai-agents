---
status: APPROVED              # APPROVED | NEEDS_CHANGES | BLOCKED
priority: P1                  # P0 | P1 | P2 (severity if not approved)
blocking: true                # true = CI blocks merge, false = advisory
reviewer: architect           # agent performing review
date: YYYY-MM-DD              # review date (ISO 8601)
pr-branch: feature/example    # (optional) git branch being reviewed
scope: [Review scope]         # (optional) brief description of review scope
---

# Architectural Review: [Title]

## Executive Summary

**VERDICT**: [PASS | NEEDS_CHANGES | BLOCKED]

[One-paragraph summary of the review outcome and overall assessment]

**Design Quality**: High | Medium | Low
**ADR Compliance**: Full | Partial | None
**Test Coverage**: Comprehensive | Adequate | Gaps
**Risk Level**: Low | Medium | High

## Design Coherence Assessment

### Architectural Fit

[Evaluate how well the change fits within the existing architecture]

- **Principle alignment**: How does this align with core architectural principles?
- **Pattern consistency**: Does this follow established patterns (ADRs, conventions)?
- **Isolation**: Are changes properly isolated to affected domains?
- **Extensibility**: Does this leave room for future extensions?

**Verdict**: PASS | NEEDS_CHANGES | BLOCKED

### Pattern Consistency

[Assess consistency with existing project patterns and conventions]

- **Code patterns**: Does code follow established conventions?
- **File organization**: Is file structure consistent with project layout?
- **Naming conventions**: Are names consistent with project standards?
- **Documentation patterns**: Is documentation style consistent?

**Verdict**: PASS | NEEDS_CHANGES | BLOCKED

### Quality Assessment

[Evaluate code quality, testing, documentation]

- **Code clarity**: Is the code clear and maintainable?
- **Error handling**: Are error cases properly handled?
- **Test coverage**: Are critical paths tested?
- **Documentation**: Are decisions documented?

**Verdict**: PASS | NEEDS_CHANGES | BLOCKED

## Detailed Analysis

### [Analysis Area 1]

[Detailed assessment of specific concern or component]

**Finding**: [What was discovered]
**Impact**: [Consequences if not addressed]
**Recommendation**: [How to address]

### [Analysis Area 2]

[Detailed assessment of specific concern or component]

**Finding**: [What was discovered]
**Impact**: [Consequences if not addressed]
**Recommendation**: [How to address]

## Required Changes (Blocking)

If `status: BLOCKED` or `status: NEEDS_CHANGES`, list required changes:

1. [First required change]
2. [Second required change]

Each item MUST include:
- What needs to change
- Why it's required (reference ADRs or principles)
- How to verify the change is complete

## Recommendations (Non-Blocking)

Suggestions for improvement or future consideration:

1. [Optional improvement]
2. [Future enhancement]

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| [Risk description] | High/Med/Low | High/Med/Low | [How to address] |

## Conclusion

[Final summary of the review. Restate verdict and key findings.]

---

## Frontmatter Reference

| Field | Required? | Valid Values | Example |
|-------|-----------|--------------|---------|
| `status` | Yes | `APPROVED`, `NEEDS_CHANGES`, `BLOCKED` | `APPROVED` |
| `priority` | Yes | `P0`, `P1`, `P2` | `P1` |
| `blocking` | Yes | `true`, `false` | `true` |
| `reviewer` | Yes | agent name | `architect` |
| `date` | Yes | `YYYY-MM-DD` | `2026-03-07` |
| `pr-branch` | No | git branch name | `feature/example` |
| `scope` | No | free text | `Schema validation` |

**CI Gate Rules:**
- If `blocking: true` AND (`status: NEEDS_CHANGES` OR `status: BLOCKED`): **merge blocked**
- If `blocking: true` AND `status: APPROVED`: **merge allowed**
- If `blocking: false`: **merge allowed** (advisory only)
