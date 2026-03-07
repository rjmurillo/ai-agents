# Skill-Cost-009: Debug Artifacts Only on Failure

**Statement**: Use if: failure() for debug artifacts to avoid unnecessary uploads

**Context**: When uploading debug logs, verbose output, or diagnostic files

**Action Pattern**:
- MUST use `if: failure()` for debug/diagnostic artifacts
- MUST NOT upload debug artifacts on success
- SHOULD use short retention (3 days) for debug artifacts
- SHOULD include run_id in artifact name for uniqueness

**Trigger Condition**:
- Uploading logs, stack traces, or debug output
- Artifact is only useful when workflow fails

**Evidence**:
- ADR-008 lines 54, 66
- COST-GOVERNANCE.md line 94

**Quantified Savings**:
- Prevents uploads on 90%+ successful runs
- Example: 100 runs/month, 10% failure rate
  - Without condition: 100 uploads × 20 MB = 2000 MB
  - With if: failure(): 10 uploads × 20 MB = 200 MB
  - Savings: 1800 MB × $0.25/GB = $0.45/month
- At 10 workflows: $4.50/month saved

**RFC 2119 Level**: MUST (ADR-008 line 66, COST-GOVERNANCE line 94)

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-008, COST-GOVERNANCE)

**Category**: CI/CD Cost Optimization

**Pattern**:
```yaml
- name: Upload Debug Logs
  # ADR-008: Debug logs only on failure
  uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: debug-logs-${{ github.run_id }}
    path: |
      logs/*.log
      !logs/verbose-*.log
    retention-days: 3
    compression-level: 9
```

**Anti-Pattern**:
```yaml
# WRONG: Always uploads regardless of success
- name: Upload Debug Logs
  uses: actions/upload-artifact@v4
  if: always()  # Wastes storage on 90% of runs
```
