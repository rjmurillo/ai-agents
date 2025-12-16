# Analysis Skills

**Extracted**: 2025-12-16
**Source**: `.agents/analysis/` directory

## Skill-Analysis-001: Capability Gap Template (88%)

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

## Related Documents

- Source: `.agents/analysis/pr43-agent-capability-gap-analysis.md`
- Related: skills-critique (conflict escalation)
