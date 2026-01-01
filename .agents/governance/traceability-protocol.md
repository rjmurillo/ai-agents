# Traceability Protocol

> **Version**: 1.0.0
> **Created**: 2025-12-31
> **Status**: Active
> **Phase**: 2 (Enhancement PROJECT-PLAN)

## Purpose

This protocol ensures all specification artifacts maintain complete traceability chains from requirements through design to implementation tasks. It prevents orphaned specs, broken references, and incomplete coverage.

## Scope

Applies to all files in:

- `.agents/specs/requirements/` (REQ-NNN)
- `.agents/specs/design/` (DESIGN-NNN)
- `.agents/specs/tasks/` (TASK-NNN)

## Quick Reference

| Document | Purpose |
|----------|---------|
| [traceability-schema.md](traceability-schema.md) | Graph structure, node/edge types, validation rules |
| [orphan-report-format.md](orphan-report-format.md) | Report format, remediation actions |
| [spec-schemas.md](spec-schemas.md) | YAML front matter schemas |

## The Traceability Chain

```text
REQ-NNN ──traces_to──> DESIGN-NNN ──traces_to──> TASK-NNN
   │                      │                         │
   └─── Requirement ──────┴─── Design ─────────────┴─── Task
```

**Rule**: Every DESIGN must have at least one REQ reference (backward) and at least one TASK reference (forward).

## Roles and Responsibilities

### spec-generator Agent

- Creates specs with valid YAML front matter
- Populates `related` field with valid references
- Ensures ID patterns match: `REQ-NNN`, `DESIGN-NNN`, `TASK-NNN`

### critic Agent

- Validates traceability before approving spec-related plans
- Blocks approval for broken references or untraced tasks
- Documents traceability issues in critique

### retrospective Agent

- Captures traceability metrics in session analysis
- Extracts learnings from traceability failures
- Recommends skill updates for recurring issues

### Pre-Commit Hook

- Runs `Validate-Traceability.ps1` when spec files are staged
- Blocks commits with broken references or untraced tasks
- Warns (but allows) orphaned specs

## Validation Script

### Basic Usage

```powershell
# Standard validation
pwsh scripts/Validate-Traceability.ps1

# Strict mode (fail on warnings)
pwsh scripts/Validate-Traceability.ps1 -Strict

# Generate markdown report
pwsh scripts/Validate-Traceability.ps1 -Format markdown > report.md

# JSON output for automation
pwsh scripts/Validate-Traceability.ps1 -Format json
```

### Exit Codes

| Code | Meaning | CI Behavior |
|------|---------|-------------|
| 0 | No errors or warnings | Pass |
| 1 | Errors found | Fail |
| 2 | Warnings only | Pass (unless `-Strict`) |

## Enforcement Points

### 1. Pre-Commit Hook

Automatic validation when spec files are staged:

```bash
# .githooks/pre-commit
# Checking specification traceability...
# Traceability validation: PASS
```

### 2. Critic Agent Review

Manual validation during plan review:

```markdown
### Traceability Validation (Spec-Layer Plans)

#### Forward Traceability (REQ -> DESIGN)
- [x] Each requirement references at least one design document

#### Backward Traceability (TASK -> DESIGN)
- [x] Each task references at least one design document

#### Traceability Verdict
[PASS] - All checks passed
```

### 3. CI Pipeline (Optional)

Add to CI for stricter enforcement:

```yaml
- name: Validate Traceability
  run: pwsh scripts/Validate-Traceability.ps1 -Strict
```

## Common Violations and Fixes

### Broken Reference (ERROR)

**Symptom**: TASK-001 references DESIGN-999 which does not exist

**Fix**: Either create the missing design or update the task's `related` field:

```yaml
# TASK-001-example.md
---
related:
  - DESIGN-001  # Changed from DESIGN-999
---
```

### Untraced Task (ERROR)

**Symptom**: TASK-005 has no design reference

**Fix**: Add `related` field with valid design ID:

```yaml
# TASK-005-example.md
---
related:
  - DESIGN-001  # Added
---
```

### Orphaned Requirement (WARNING)

**Symptom**: REQ-003 has no design implementing it

**Fix**: Either create a design that references it or deprecate if obsolete:

```yaml
# REQ-003-example.md
---
status: deprecated  # If no longer needed
---
```

### Orphaned Design (WARNING)

**Symptom**: DESIGN-002 has no tasks implementing it

**Fix**: Either create tasks that reference it or deprecate if obsolete.

## YAML Front Matter Requirements

### Requirement (REQ)

```yaml
---
type: requirement
id: REQ-001
status: draft | review | approved | implemented
related:
  - DESIGN-001  # Designs that address this requirement
---
```

### Design (DESIGN)

```yaml
---
type: design
id: DESIGN-001
status: draft | review | approved | implemented
related:
  - REQ-001     # Requirements addressed
  - REQ-002
  - TASK-001    # Tasks implementing (optional, derived)
  - TASK-002
---
```

### Task (TASK)

```yaml
---
type: task
id: TASK-001
status: pending | in_progress | done | blocked
related:
  - DESIGN-001  # Design being implemented
---
```

## Metrics and Reporting

### Key Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| Valid Chains | 100% | Complete REQ->DESIGN->TASK traces |
| Orphaned REQs | 0 | Requirements without designs |
| Orphaned Designs | 0 | Designs without tasks |
| Broken References | 0 | Invalid spec IDs |
| Untraced Tasks | 0 | Tasks without design reference |

### Reporting

Generate a traceability report:

```powershell
pwsh scripts/Validate-Traceability.ps1 -Format markdown > .agents/reports/traceability-$(Get-Date -Format 'yyyy-MM-dd').md
```

## Integration with Workflows

### Feature Development Flow

```text
1. Create REQ-NNN (requirement)
2. Create DESIGN-NNN referencing REQ-NNN
3. Create TASK-NNN referencing DESIGN-NNN
4. Pre-commit validates traceability
5. Critic validates during plan review
6. Retrospective captures metrics
```

### Spec Modification Flow

```text
1. Modify spec file
2. Update related field if references change
3. Run validation: pwsh scripts/Validate-Traceability.ps1
4. Fix any errors before committing
5. Pre-commit hook validates on commit
```

## Troubleshooting

### "Validation script not found"

Ensure you're in the repository root:

```bash
cd /path/to/ai-agents
pwsh scripts/Validate-Traceability.ps1
```

### "PowerShell not available"

Install PowerShell:

- Linux/macOS: <https://docs.microsoft.com/en-us/powershell/scripting/install/installing-powershell>
- Windows: Built-in

### "Pre-commit hook not running"

Configure git to use the hooks:

```bash
git config core.hooksPath .githooks
```

## References

- [traceability-schema.md](traceability-schema.md) - Detailed graph schema
- [orphan-report-format.md](orphan-report-format.md) - Report format
- [spec-schemas.md](spec-schemas.md) - YAML schema definitions
- [EARS format](ears-format.md) - Requirement statement patterns
