# Skill-Cost-008: No Compression Mandate for Artifacts

**Statement**: No authority mandates `compression-level`. ADR-015 weighed
compression as a cost lever and adopted shorter retention instead.

**Context**: When uploading artifacts in GitHub Actions workflows

**Action Pattern**:
- SHOULD reach for `retention-days` first; that is the lever ADR-015 adopted
- MUST NOT cite an ADR for a compression mandate; none grants one
- Setting `compression-level` is neither required nor forbidden here; no
  authority rules on it, so treat it as an ordinary engineering choice

**Trigger Condition**:
- Adding `actions/upload-artifact` to a workflow
- Reviewing a change that proposes compressing artifacts to cut cost

**Evidence**:
- ADR-015, Alternatives Considered: "Compress artifacts | Reduced storage |
  Decompression overhead | Minimal benefit for text files". It appears in the
  alternatives table, in the Why Not Chosen column.
- ADR-015, Decision: the adopted lever is shorter retention, not compression.
- Repository practice: 14 files under `.github/workflows/` plus the
  `.github/actions/agent-review` composite action use
  `actions/upload-artifact`; `compression-level` appears zero times
  anywhere under `.github/`.
- Counter-evidence, recorded rather than suppressed:
  `docs/COST-GOVERNANCE.md:202` recommends "Compress large artifacts
  before upload". That is a best-practice list, not an ADR, and it does
  not name `compression-level`. It is why this memory records the absence
  of a mandate rather than a prohibition.

**Correction History**:

This memory previously asserted `MUST set compression-level: 9` at RFC 2119
MUST level, citing "ADR-008 line 64". That citation was checked and failed:
ADR-008 is "Protocol Automation via Lifecycle Hooks", its line 64 is blank,
and it contains no compression content. The secondary citation,
"COST-GOVERNANCE.md artifact hygiene", is ambiguous: two files carry that
name. `.agents/governance/COST-GOVERNANCE.md` contains no compression
content; `docs/COST-GOVERNANCE.md:202` recommends compressing large
artifacts but grants no mandate and names no parameter. Neither supports a
MUST. The ADR that owns artifact storage, ADR-015, weighed compression and
adopted shorter retention instead. An agent retrieving the old text would
have edited 14 workflows to satisfy a rule no authority granted.

A first pass at this correction over-corrected, replacing the fabricated
MUST with a SHOULD NOT. That was the same error pointed the other way: no
authority forbids compression either. Absence of a mandate is the finding.

**Atomicity**: 99%

**Tag**: corrective

**Impact**: 7/10

**Created**: 2025-12-20

**Corrected**: 2026-07-17

**Validated**: 1 (ADR-015 Alternatives Considered)

**Actionable**: no; this record exists to stop a fabricated rule returning

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
