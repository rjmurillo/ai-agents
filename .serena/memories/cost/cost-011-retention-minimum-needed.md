# Skill-Cost-011: Artifact Retention Minimum Needed

**Statement**: Set retention-days to minimum needed, default ≤7 days

**Context**: When uploading artifacts in GitHub Actions workflows

**Action Pattern**:
- MUST set `retention-days` explicitly (no default)
- MUST use ≤7 days for most artifacts
- SHOULD use 1 day for build outputs consumed by dependent jobs
- SHOULD use 3 days for debug logs
- MAY use 30 days for release artifacts with justification

**Trigger Condition**:
- Adding artifact upload to workflow
- Default retention would be excessive

**Evidence**:
- ADR-008 lines 17, 50-56
- COST-GOVERNANCE.md line 17

**Quantified Savings**:
- Example: 100 MB artifact, 50 runs/month
  - 90-day retention: 5000 MB-days × $0.000336/MB-day = $1.68/month
  - 7-day retention: 350 MB-days × $0.000336/MB-day = $0.12/month
  - Savings: $1.56/month per workflow (93% reduction)

**RFC 2119 Level**: MUST (ADR-008 line 17)

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-008, COST-GOVERNANCE)

**Category**: CI/CD Cost Optimization

**Retention Guidelines**:
| Artifact Type | Retention | Justification |
|---------------|-----------|---------------|
| Build outputs (consumed by workflow) | 1 day | Ephemeral |
| Debug logs | 3 days | Recent debugging |
| Test results | 7 days | PR merge cycle |
| Coverage reports | 7 days | Trend tracking |
| Release binaries | 30 days | Distribution window |

**Pattern**:
```yaml
- name: Upload Test Results
  uses: actions/upload-artifact@v4
  with:
    name: test-results
    retention-days: 7  # Explicit, not default
```

**Comment Requirement**:
```yaml
# ADR-008: 7-day retention aligns with PR merge cycle
retention-days: 7
```
