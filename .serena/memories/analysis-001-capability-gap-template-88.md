# Analysis: Capability Gap Template 88

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

## Related

- [analysis-001-comprehensive-analysis-standard](analysis-001-comprehensive-analysis-standard.md)
- [analysis-002-comprehensive-analysis-standard-95](analysis-002-comprehensive-analysis-standard-95.md)
- [analysis-002-rca-before-implementation](analysis-002-rca-before-implementation.md)
- [analysis-003-related-issue-discovery](analysis-003-related-issue-discovery.md)
- [analysis-004-verify-codebase-state](analysis-004-verify-codebase-state.md)
