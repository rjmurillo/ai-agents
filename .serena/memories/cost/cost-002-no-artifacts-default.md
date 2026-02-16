# Skill-Cost-002: No Artifacts by Default

**Statement**: Workflows MUST NOT upload artifacts unless justified with ADR-008 comment

**Context**: When writing GitHub Actions workflows

**Action Pattern**:
- MUST NOT include `actions/upload-artifact` without documented justification
- MUST add ADR-008 comment explaining why artifact is needed
- MUST set `retention-days` to minimum needed (≤7 days for most)
- MUST use `compression-level: 9` for text artifacts
- MUST use `if: failure()` for debug artifacts

**Trigger Condition**:
- Adding artifact upload to workflow
- Reviewing PR with artifact upload

**Evidence**:
- ADR-008 Artifact Storage Minimization
- COST-GOVERNANCE.md lines 46-48

**Quantified Savings**:
- 60-80% reduction in storage costs
- $0.25/GB/month storage cost avoided
- For 10GB artifacts with 90-day retention: ~$2.50/month vs 7-day: ~$0.20/month

**RFC 2119 Level**: MUST (ADR-008 line 45)

**Atomicity**: 96%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-008 acceptance, COST-GOVERNANCE policy)

**Category**: CI/CD Cost Optimization

**Anti-Pattern**:
```yaml
# WRONG: No justification, long retention, no compression
- uses: actions/upload-artifact@v4
  with:
    name: logs
    path: logs/
    retention-days: 90
```

**Correct Pattern**:
```yaml
# ADR-008: Test results justified for CI visibility
# 7-day retention aligns with PR merge cycle
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: test-results
    path: TestResults/*.xml
    retention-days: 7
    compression-level: 9
```
