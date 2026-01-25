# Skill-Analysis-002: Comprehensive Analysis Standard

**Statement**: Analysis documents MUST include multiple options with trade-offs, explicit recommendations, and implementation specifications detailed enough for direct implementation.

**Context**: When analyst creates analysis documents for later implementation.

**Evidence**: Analyses 002-004 provided complete specs that implementers followed exactly without clarification. 100% implementation accuracy across Sessions 19-21.

**Atomicity**: 95%

**Impact**: 9/10 - Enables 100% implementation accuracy

## Required Structure

1. **Options Analysis**: 3-5 alternative approaches
2. **Trade-off Tables**: Pros/cons for each option
3. **Evidence**: Verified facts, not assumptions
4. **Recommendation**: Explicit choice with rationale
5. **Implementation Specs**: Detailed enough to implement without clarification

## Evidence

| Analysis | Size | Options | Session | Result |
|----------|------|---------|---------|--------|
| 002 | 857 lines | 5 | 19 | 100% match |
| 003 | 987 lines | design + risks | 20 | 100% match |
| 004 | 1,347 lines | 3 + appendices | 21 | 100% match |

## Related

- [analysis-001-comprehensive-analysis-standard](analysis-001-comprehensive-analysis-standard.md)
- [analysis-002-rca-before-implementation](analysis-002-rca-before-implementation.md)
- [analysis-003-related-issue-discovery](analysis-003-related-issue-discovery.md)
- [analysis-004-verify-codebase-state](analysis-004-verify-codebase-state.md)
- [analysis-gap-template](analysis-gap-template.md)
