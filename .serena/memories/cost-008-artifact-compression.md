# Skill-Cost-008: Artifact Compression Required

**Statement**: Use compression-level 9 for all text-based artifacts

**Context**: When uploading artifacts in GitHub Actions workflows

**Action Pattern**:
- MUST set `compression-level: 9` for text artifacts (logs, XML, JSON, markdown)
- SHOULD NOT compress already-compressed formats (zip, tar.gz, images)
- MUST target specific files, not entire directories

**Trigger Condition**:
- Adding `actions/upload-artifact` to workflow
- Uploading text-based artifacts (test results, logs, reports)

**Evidence**:
- ADR-008 line 64
- COST-GOVERNANCE.md artifact hygiene

**Quantified Savings**:
- Text compression: 70-90% size reduction typical
- Example: 100 MB logs → 15 MB compressed
- Storage cost: $0.25/GB/month
  - Uncompressed: 100 MB × $0.25 = $0.025/month
  - Compressed: 15 MB × $0.25 = $0.004/month
  - Savings: $0.021/month per artifact
- At 100 artifacts/month: $2.10/month saved

**RFC 2119 Level**: MUST (ADR-008 line 64)

**Atomicity**: 99%

**Tag**: helpful

**Impact**: 7/10

**Created**: 2025-12-20

**Validated**: 1 (ADR-008)

**Category**: CI/CD Cost Optimization

**Pattern**:
```yaml
- name: Upload Test Results
  uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: TestResults/*.xml
    retention-days: 7
    compression-level: 9  # MUST for text artifacts
```

**Skip Compression**:
```yaml
# Already compressed - no benefit from re-compression
path: release/*.tar.gz
compression-level: 0
```
