# Analysis Skills

**Extracted**: 2025-12-16
**Source**: `.agents/analysis/` directory

## Skill-Analysis-001: Capability Gap Template (88%)

**Note**: This skill was originally Skill-Analysis-001. Renamed to avoid collision with Comprehensive Analysis Standard skill.

**Statement**: Structure gap analysis with ID, Severity, Root Cause, Affected Agents, Remediation

**Context**: Post-failure analysis and root cause investigation

**Evidence**: PR43 capability gap analysis used structured template

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Template**:

```markdown
## Gap [ID]: [Short Title]

**Severity**: Critical | High | Medium | Low
**Root Cause**: [Why the gap exists]
**Affected Agents**: [List of impacted agents]
**Impact**: [What fails when this gap exists]
**Remediation**: [Specific fix with files/changes]
**Verification**: [How to confirm fix works]
```

**Use Case**: After PR failures to systematically identify missing capabilities

**Source**: `.agents/analysis/pr43-agent-capability-gap-analysis.md`

---

## Skill-Analysis-002: Comprehensive Analysis Standard (95%)

**Statement**: Analysis documents MUST include multiple options with trade-offs, explicit recommendations, and implementation specifications detailed enough for direct implementation

**Context**: When analyst creates analysis documents for later implementation

**Evidence**: Analyses 002-004 provided complete specs that implementers followed exactly without clarification. 100% implementation accuracy across Sessions 19-21.

**Atomicity**: 95%

- Single concept (analysis standard) ✓
- Specific requirements (options, trade-offs, recommendations, specs) ✓
- Actionable (create comprehensive analysis) ✓
- Length: 16 words (-5%)

**Tag**: helpful

**Impact**: 9/10 - Enables 100% implementation accuracy

**Required Structure**:

1. **Options Analysis**: 3-5 alternative approaches
2. **Trade-off Tables**: Pros/cons for each option
3. **Evidence**: Verified facts, not assumptions
4. **Recommendation**: Explicit choice with rationale
5. **Implementation Specs**: Detailed enough to implement without clarification

**Example Evidence**:

- Analysis 002 (857 lines, 5 options) → Session 19: 100% specification match
- Analysis 003 (987 lines, design + risks) → Session 20: 100% specification match
- Analysis 004 (1,347 lines, 3 options + appendices) → Session 21: 100% specification match

**Validation**: 3 (Sessions 19, 20, 21)

**Created**: 2025-12-18

---

## Related Documents

- Source: `.agents/analysis/pr43-agent-capability-gap-analysis.md`
- Source: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`
- Related: skills-critique (conflict escalation)
- Related: skills-planning (Skill-Planning-003 parallel exploration)
