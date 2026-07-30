# Skill-Cost-002: Artifacts Earn Their Retention

**Statement**: Artifact uploads MUST set the shortest retention that serves
their purpose; ADR-015 decided the retention numbers, not a ban on artifacts

**Context**: When writing GitHub Actions workflows

**Action Pattern**:
- MUST set `retention-days` to the minimum needed; ADR-015 Decision sets
  7 days for test results and metrics reports, 1 day for operational output
- SHOULD say in a comment why the artifact is needed; no ADR requires this,
  it just keeps the next reader from guessing
- SHOULD gate debug-only uploads on failure (see Skill-Cost-009)

**Trigger Condition**:
- Adding artifact upload to workflow
- Reviewing PR with artifact upload

**Evidence**:
- ADR-015 Artifact Storage Minimization, Decision section, for the retention
  numbers only
- `.agents/governance/COST-GOVERNANCE.md`, "Use artifact retention policies
  to limit storage costs"
- Counter-evidence: ADR-015 Alternatives Considered lists "Disable
  artifacts" with "Too aggressive; artifacts provide value". No authority
  grants a no-artifacts default, which is why this memory was renamed.

**Quantified Savings**:
- 60-80% reduction in storage costs
- $0.25/GB/month storage cost avoided
- For 10GB artifacts with 90-day retention: ~$2.50/month vs 7-day: ~$0.20/month

**RFC 2119 Level**: MUST for the retention number (ADR-015 Decision);
SHOULD for the rest, which no authority mandates

**Atomicity**: 96%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-015 acceptance, COST-GOVERNANCE policy)

**Category**: CI/CD Cost Optimization

**Anti-Pattern**:
```yaml
# WRONG: unexplained, and 90-day retention on CI output
- uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  with:
    name: logs
    path: logs/
    retention-days: 90
```

**Correct Pattern**:
```yaml
# ADR-015: Test results justified for CI visibility
# 7-day retention aligns with PR merge cycle
- uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  if: always()
  with:
    name: test-results
    path: TestResults/*.xml
    retention-days: 7
```
