# Skill-Cost-002: Artifacts Earn Their Retention

**Statement**: ADR-015 sets 1-day retention for operational artifacts and
7-day retention for test results and metrics reports. It does not ban
artifacts or set retention for other artifact types.

**Context**: When writing GitHub Actions workflows

**Action Pattern**:
- MUST use 1 day for operational artifacts and 7 days for test results and
  metrics reports
- For other artifact types, choose retention from the documented consumer
  need; no repository-wide duration exists
- Gate debug-only uploads on failure when no success-case consumer exists
  (see Skill-Cost-009)

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

**RFC 2119 Level**: MUST for the three artifact classes in ADR-015; none for
other artifact types or failure-only upload gating

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
# ADR-015: Keep test results for 7 days to debug recent failures
# Older results remain in git history
- uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  if: always()
  with:
    name: test-results
    path: TestResults/*.xml
    retention-days: 7
```
