# CI Matrix Job Artifacts

## Skill-CI-Matrix-Output-001: Matrix Jobs Use Artifacts for Data Passing (98%)

**Statement**: GitHub Actions matrix jobs only expose ONE leg's outputs; use artifacts for reliable data passing.

**Evidence**: Session 07 - Matrix jobs (security, qa, analyst) wrote outputs but only ONE leg's outputs available. GitHub Community Discussion #17245 confirms.

**Pattern**:

```yaml
# Matrix job: Save to file and upload artifact
review:
  strategy:
    matrix:
      agent: [security, qa, analyst]
  steps:
    - run: echo "$FINDINGS" > ${{ matrix.agent }}-findings.txt
    - uses: actions/upload-artifact@v4
      with:
        name: ${{ matrix.agent }}-findings
        path: ${{ matrix.agent }}-findings.txt

# Aggregate job: Download all artifacts
aggregate:
  needs: review
  steps:
    - uses: actions/download-artifact@v4
      with:
        pattern: '*-findings'
        merge-multiple: true
    - run: cat security-findings.txt qa-findings.txt analyst-findings.txt
```

**Key Points**:

- Matrix output behavior is non-deterministic
- Only ONE matrix leg's outputs are exposed
- Artifacts provide reliable cross-job data passing
- Use `merge-multiple: true` to combine multiple artifacts
