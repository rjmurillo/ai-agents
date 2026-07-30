# Skill-Cost-009: Debug Artifacts Only on Failure

**Statement**: Use if: failure() for debug artifacts to avoid unnecessary uploads

**Context**: When uploading debug logs, verbose output, or diagnostic files

**Action Pattern**:
- SHOULD use `if: failure()` for debug/diagnostic artifacts
- SHOULD NOT upload debug artifacts on success
- SHOULD use short retention (3 days) for debug artifacts
- SHOULD include run_id in artifact name for uniqueness

**Trigger Condition**:
- Uploading logs, stack traces, or debug output
- Artifact is only useful when workflow fails

**Evidence**:
- ADR-015 Artifact Storage Minimization establishes the minimize-artifacts
  posture this follows. No ADR mandates the failure condition itself, so this
  is a practice, not a rule.
- Repository practice: no workflow currently gates an upload on `failure()`

**Quantified Savings**:
- Prevents uploads on 90%+ successful runs
- Example: 100 runs/month, 10% failure rate
  - Without condition: 100 uploads × 20 MB = 2000 MB
  - With if: failure(): 10 uploads × 20 MB = 200 MB
  - Savings: 1800 MB × $0.25/GB = $0.45/month
- At 10 workflows: $4.50/month saved

**RFC 2119 Level**: SHOULD (no ADR mandates this; ADR-015 sets the posture)

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Validated**: 1 (ADR-015 posture)

**Category**: CI/CD Cost Optimization

**Pattern**:
```yaml
- name: Upload Debug Logs
  # Debug-only artifact; skip the upload on success to avoid storing noise
  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  if: failure()
  with:
    name: debug-logs-${{ github.run_id }}
    path: |
      logs/*.log
      !logs/verbose-*.log
    retention-days: 3
```

**Anti-Pattern**:
```yaml
# WRONG: Always uploads regardless of success
- name: Upload Debug Logs
  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  if: always()  # Wastes storage on 90% of runs
```
