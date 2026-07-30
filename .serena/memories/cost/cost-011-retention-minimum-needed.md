# Skill-Cost-011: Artifact Retention Minimum Needed

**Statement**: Use ADR-015 retention values for the artifact classes it
governs. Derive other retention periods from documented consumer need.

**Context**: When uploading artifacts in GitHub Actions workflows

**Action Pattern**:
- MUST use 1 day for operational artifacts
- MUST use 7 days for test results and metrics reports
- For other artifact types, document the consumer need and choose retention
  from that need; ADR-015 sets no default

**Trigger Condition**:
- Adding artifact upload to workflow
- Default retention would be excessive

**Evidence**:
- ADR-015 Context, "Minimal retrieval needs: Most artifacts are for
  debugging and rarely accessed after 7 days"
- ADR-015 Decision: test results and metrics reports both reduced to 7 days
- COST-GOVERNANCE.md line 121 ("Use artifact retention policies")

**Quantified Savings**:
- Example: 100 MB artifact, 50 runs/month
  - 90-day retention: 5000 MB-days × $0.000336/MB-day = $1.68/month
  - 7-day retention: 350 MB-days × $0.000336/MB-day = $0.12/month
  - Savings: $1.56/month per workflow (93% reduction)

**RFC 2119 Level**: MUST only for operational artifacts, test results, and
metrics reports in ADR-015; none for other artifact types

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-015, COST-GOVERNANCE)

**Category**: CI/CD Cost Optimization

**Retention Guidelines**:
| Artifact Type | Retention | Justification |
|---------------|-----------|---------------|
| Operational artifacts | 1 day | Needed within the same workflow |
| Test results | 7 days | Debug recent failures |
| Metrics reports | 7 days | Review the latest report |
| Other artifacts | No repository default | Document consumer need |

**Pattern**:
```yaml
- name: Upload Test Results
  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  with:
    name: test-results
    retention-days: 7  # Explicit, not default
```

**Example Rationale**:
```yaml
# ADR-015: Keep test results for 7 days to debug recent failures
retention-days: 7
```
