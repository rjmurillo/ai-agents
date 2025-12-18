# Consistency Protocol

## Purpose

This document defines the validation procedure for ensuring cross-document consistency across agent-generated artifacts. Consistency validation prevents scope drift, orphaned tasks, and broken cross-references.

---

## Checkpoint Locations

Consistency validation occurs at specific points in the workflow.

### Checkpoint 1: Post-Task-Generator (Pre-Critic)

**Trigger**: task-generator completes work breakdown

**Location in workflow**:

```text
roadmap -> explainer -> task-generator -> [CHECKPOINT 1] -> critic -> implementer
```

**What to validate**:

- Epic-to-PRD scope alignment
- PRD-to-tasks coverage
- Naming convention compliance
- Cross-reference validity

### Checkpoint 2: Post-Implementation (Pre-QA)

**Trigger**: implementer completes code changes

**Location in workflow**:

```text
critic -> implementer -> [CHECKPOINT 2] -> qa
```

**What to validate**:

- All tasks from PRD have been addressed
- Implementation matches approved plan
- No scope creep beyond PRD boundaries

---

## Validation Checklist

### Pre-Critic Validation (Checkpoint 1)

| Category | Check | How to Verify |
|----------|-------|---------------|
| **Scope Alignment** | Epic scope matches PRD scope | Compare epic outcomes to PRD requirements |
| **Coverage** | All PRD requirements have tasks | Map each requirement to task(s) |
| **Estimates** | Task estimates align with PRD complexity | Sum task estimates vs PRD effort |
| **Naming** | EPIC-NNN, ADR-NNN patterns followed | Regex match against naming-conventions.md |
| **References** | Cross-references point to existing files | File existence check |
| **Traceability** | No orphaned tasks | Each task traces to a requirement |
| **Memory** | Entity observations are current | Check for stale observations (>30 days) |
| **Spec Layer** | REQ→DESIGN→TASK chain complete | Validate 3-tier traceability (Phase 1+) |

### Post-Implementation Validation (Checkpoint 2)

| Category | Check | How to Verify |
|----------|-------|---------------|
| **Task Completion** | All P0/P1 tasks completed | Check task status in tasks-*.md |
| **Plan Adherence** | Implementation follows approved plan | Compare code changes to plan |
| **Scope Boundaries** | No changes outside PRD scope | Review changed files against scope |
| **Documentation** | Code comments match PRD language | Spot check key files |

---

## Inconsistency Response Procedure

When validation finds inconsistencies, follow this escalation path.

### Severity Classification

| Severity | Definition | Examples |
|----------|------------|----------|
| **Minor** | Cosmetic or easily fixed | Typo in reference, missing date |
| **Major** | Scope or coverage gap | Missing task for requirement |
| **Critical** | Fundamental misalignment | PRD contradicts epic outcomes |

### Response by Severity

| Severity | Action | Who Handles |
|----------|--------|-------------|
| **Minor** | Fix inline, proceed | Orchestrator |
| **Major** | Return to planner | Planner with specific issues |
| **Critical** | Escalate to architect | May require epic revision |

### Inconsistency Report Format

When returning work for revision, use this format:

```markdown
## Consistency Validation Report

**Checkpoint**: [1: Pre-Critic | 2: Post-Implementation]
**Date**: [YYYY-MM-DD]
**Status**: FAILED

### Artifacts Validated

| Artifact | Path | Status |
|----------|------|--------|
| Epic | `roadmap/EPIC-NNN-*.md` | [OK/ISSUE] |
| PRD | `planning/prd-*.md` | [OK/ISSUE] |
| Tasks | `planning/tasks-*.md` | [OK/ISSUE] |

### Inconsistencies Found

| ID | Severity | Document | Issue | Required Action |
|----|----------|----------|-------|-----------------|
| 1 | [Minor/Major/Critical] | [path] | [description] | [what to fix] |
| 2 | ... | ... | ... | ... |

### Routing Decision

**Return to**: [planner | architect | roadmap]
**Reason**: [explanation]
**Expected Deliverable**: [what the receiving agent should produce]
```

---

## Common Inconsistencies

### Scope Drift

**Symptom**: PRD includes requirements not in epic outcomes.

**Detection**: Compare epic "Success Criteria" to PRD "Requirements" section.

**Resolution**: Either update epic scope (with user approval) or remove PRD requirements.

### Orphaned Tasks

**Symptom**: Tasks exist that don't map to any PRD requirement.

**Detection**: For each task, verify it traces to a specific requirement.

**Resolution**: Either add missing requirement to PRD or remove orphaned task.

### Estimate Mismatch

**Symptom**: Sum of task estimates exceeds PRD effort assessment.

**Detection**: Sum all task story points/hours vs PRD complexity rating.

**Resolution**: Re-evaluate task breakdown or update PRD complexity.

### Broken References

**Symptom**: Cross-reference points to non-existent file.

**Detection**: File existence check for all paths in documents.

**Resolution**: Fix path or create missing artifact.

### Naming Violations

**Symptom**: File names don't match declared patterns.

**Detection**: Regex validation against naming-conventions.md.

**Resolution**: Rename file to comply with convention.

### Spec Layer Traceability Gaps

**Symptom**: REQ/DESIGN/TASK artifacts missing cross-references (Phase 1+).

**Detection**: Parse YAML front matter `related:` fields and validate chains.

**Resolution**:
1. Every TASK must link to at least one DESIGN
2. Every DESIGN must link to at least one REQ
3. Forward and backward references must match

**Example**:
```yaml
# In TASK-001-*.md
related:
  - DESIGN-001  # Must exist and reference this task back

# In DESIGN-001-*.md
related:
  - REQ-001     # Must exist
  - TASK-001    # Optional forward reference
```

---

## Automation Support

### Validation Script

Location: `scripts/Validate-Consistency.ps1`

Capabilities:

```powershell
# Validate a specific feature's artifacts
.\validate-consistency.ps1 -Feature "user-authentication"

# Validate all artifacts
.\validate-consistency.ps1 -All

# Output formats
.\validate-consistency.ps1 -Feature "auth" -Format "markdown"
.\validate-consistency.ps1 -Feature "auth" -Format "json"
```

### CI Integration

Consistency validation can be integrated into CI:

```yaml
- name: Validate Consistency
  run: pwsh scripts/Validate-Consistency.ps1 -All -CI
```

---

## Checkpoint Bypass

In rare cases, checkpoints may be bypassed with explicit justification.

### Valid Bypass Reasons

1. **Hotfix**: Critical production issue requires immediate action
2. **Experimental**: Proof-of-concept work not intended for merge
3. **User Override**: User explicitly requests bypass

### Bypass Documentation

When bypassing, document in the handoff file:

```markdown
## Checkpoint Bypass

**Checkpoint**: [1 | 2]
**Reason**: [Hotfix | Experimental | User Override]
**Justification**: [specific explanation]
**Risk Acknowledged**: [what could go wrong]
**Remediation Plan**: [when/how to validate retroactively]
```

---

## Related Documents

- [Naming Conventions](./naming-conventions.md) - Artifact naming patterns
- [Orchestrator](../../src/claude/orchestrator.md) - Checkpoint integration
- [Critic Agent](../../src/claude/critic.md) - Plan validation details
- [Agent Design Principles](./agent-design-principles.md) - Consistency principle

---

*Version: 1.0*
*Established: 2025-12-16*
*GitHub Issue: #44*
