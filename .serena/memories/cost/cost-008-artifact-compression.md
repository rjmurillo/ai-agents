# Skill-Cost-008: Artifact Compression Was Considered and Rejected

**Statement**: Do not add `compression-level` to artifact uploads. ADR-015
evaluated compression and did not adopt it.

**Context**: When uploading artifacts in GitHub Actions workflows

**Action Pattern**:
- SHOULD NOT add `compression-level` to `actions/upload-artifact` steps
- SHOULD reduce `retention-days` instead; that is the lever ADR-015 chose
- MUST NOT cite an ADR for a compression mandate; none grants one

**Trigger Condition**:
- Adding `actions/upload-artifact` to a workflow
- Reviewing a change that proposes compressing artifacts to cut cost

**Evidence**:
- ADR-015, Alternatives Considered: "Compress artifacts | Reduced storage |
  Decompression overhead | Minimal benefit for text files". It appears in the
  alternatives table, in the Why Not Chosen column.
- ADR-015, Decision: the adopted lever is shorter retention, not compression.
- Repository practice: 14 workflow files use `actions/upload-artifact` and
  none sets `compression-level`.

**Correction History**:

This memory previously asserted `MUST set compression-level: 9` at RFC 2119
MUST level, citing "ADR-008 line 64". That citation was checked and failed:
ADR-008 is "Protocol Automation via Lifecycle Hooks", its line 64 is blank,
and it contains no compression content. The secondary citation,
"COST-GOVERNANCE.md artifact hygiene", also failed; that file contains no
compression content. The ADR that owns artifact storage, ADR-015, evaluated
compression and did not adopt it. An agent retrieving the old text would have
edited 14 workflows to satisfy a rule no authority granted.

**Atomicity**: 99%

**Tag**: corrective

**Impact**: 7/10

**Created**: 2025-12-20

**Corrected**: 2026-07-17

**Validated**: 1 (ADR-015 Alternatives Considered)

**Category**: CI/CD Cost Optimization

**Pattern**:

```yaml
- name: Upload Test Results
  uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: TestResults/*.xml
    retention-days: 7  # ADR-015: shorter retention is the adopted lever
```
