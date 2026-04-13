# Governance: Legacy Session Artifact Remediation

## Skill-Governance-010: Legacy Session Artifact Remediation

**Statement**: When validation fails on legacy session logs, check if failures reference pre-ADR requirements and update to N/A with ADR reference

**Atomicity**: 91%

**Context**: Session validation fails on HANDOFF.md update requirement

**Evidence**: PR #235 - Session created before ADR-014 required HANDOFF.md update, fixed by marking as N/A with ADR-014 reference (commit d5f1281)

**Trigger**: Session end validation fails with "Update HANDOFF.md" marked as MUST complete

**Related Skills**:
- Skill-Protocol-006 (legacy session grandfathering)
- ADR-014 (distributed handoff - HANDOFF.md read-only on feature branches)

**SMART Validation**:
- Specific: Y - One concept: legacy session remediation
- Measurable: Y - PR #235 fixed, validation now passes
- Attainable: Y - Simple text edit to session log
- Relevant: Y - Applies to all pre-ADR-014 sessions
- Timely: Y - Trigger: Session validation fails on HANDOFF.md