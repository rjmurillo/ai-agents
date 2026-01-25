# Traceability Graph Schema

> **Version**: 1.0.0
> **Created**: 2025-12-31
> **Status**: Active
> **Related**: [enhancement-PROJECT-PLAN.md](../planning/enhancement-PROJECT-PLAN.md) Phase 2

## Overview

This document defines the traceability graph structure used to validate cross-references between specification artifacts (requirements, designs, and tasks).

## Graph Structure

### Node Types

| Type | ID Pattern | Location | Description |
|------|------------|----------|-------------|
| REQ | `REQ-NNN` | `.agents/specs/requirements/` | EARS format requirements |
| DESIGN | `DESIGN-NNN` | `.agents/specs/design/` | Design documents |
| TASK | `TASK-NNN` | `.agents/specs/tasks/` | Atomic work items |

### Edge Types

| Edge | From | To | Meaning |
|------|------|-----|---------|
| `traces_to` | TASK | DESIGN | Task implements part of design |
| `traces_to` | DESIGN | REQ | Design addresses requirement |
| `implements` | TASK | REQ | Direct implementation reference |
| `depends_on` | Any | Any | Prerequisite relationship |

### YAML Front Matter Schema

Each spec file MUST have YAML front matter with these fields:

```yaml
---
type: requirement | design | task
id: REQ-NNN | DESIGN-NNN | TASK-NNN
status: draft | review | approved | implemented | complete
related:
  - REQ-NNN     # For designs: requirements addressed
  - DESIGN-NNN  # For tasks: designs implemented
---
```

## Traceability Rules

### Rule 1: Forward Traceability

Every REQUIREMENT must trace forward to at least one DESIGN.

```text
REQ-001 → DESIGN-001 (required)
REQ-001 → (none)     (VIOLATION: orphaned requirement)
```

### Rule 2: Backward Traceability

Every TASK must trace backward to at least one DESIGN.

```text
TASK-001 → DESIGN-001 (required)
TASK-001 → (none)     (VIOLATION: untraced task)
```

### Rule 3: Complete Chain

Every DESIGN must have both:
- At least one REQ reference (backward)
- At least one TASK reference (forward)

```text
REQ-001 → DESIGN-001 → TASK-001 (complete chain)
REQ-001 → DESIGN-001 → (none)   (VIOLATION: orphaned design)
```

### Rule 4: Reference Validity

All referenced IDs must exist as files.

```text
TASK-001 references DESIGN-999
DESIGN-999 file exists?
  YES → valid
  NO  → VIOLATION: broken reference
```

### Rule 5: Status Consistency

Completed status must propagate consistently:

| If | Then |
|-----|------|
| TASK status = complete | DESIGN should be implemented or complete |
| DESIGN status = implemented | REQ should be implemented |
| All TASKs for DESIGN complete | DESIGN should be complete |

## Orphan Detection Algorithm

```text
FUNCTION DetectOrphans(specs):
    orphaned_reqs = []
    orphaned_designs = []
    untraced_tasks = []
    broken_refs = []

    # Build reference index
    req_refs = {}      # REQ-ID → [DESIGN-IDs that reference it]
    design_refs = {}   # DESIGN-ID → [TASK-IDs that reference it]

    FOR each task in specs.tasks:
        FOR each design_id in task.related:
            IF design_id not in specs.designs:
                broken_refs.append((task.id, design_id))
            ELSE:
                design_refs[design_id].append(task.id)

    FOR each design in specs.designs:
        FOR each req_id in design.related:
            IF req_id not in specs.requirements:
                broken_refs.append((design.id, req_id))
            ELSE:
                req_refs[req_id].append(design.id)

    # Detect orphans
    FOR each req in specs.requirements:
        IF req.id not in req_refs OR len(req_refs[req.id]) == 0:
            orphaned_reqs.append(req.id)

    FOR each design in specs.designs:
        IF design.id not in design_refs OR len(design_refs[design.id]) == 0:
            orphaned_designs.append(design.id)

    FOR each task in specs.tasks:
        IF len(task.related) == 0:
            untraced_tasks.append(task.id)

    RETURN {
        orphaned_reqs,
        orphaned_designs,
        untraced_tasks,
        broken_refs
    }
```

## Graph Visualization

```text
                    REQUIREMENTS LAYER
                    ┌─────────────┐
                    │   REQ-001   │
                    │   REQ-002   │
                    └──────┬──────┘
                           │ traces_to
                           ▼
                    DESIGN LAYER
                    ┌─────────────┐
                    │  DESIGN-001 │
                    └──────┬──────┘
                           │ traces_to
                           ▼
                    TASK LAYER
          ┌────────┬────────┬────────┐
          ▼        ▼        ▼        ▼
     ┌────────┐┌────────┐┌────────┐
     │TASK-001││TASK-002││TASK-003│
     └────────┘└────────┘└────────┘
```

## Validation Levels

| Level | Checks | Exit Code |
|-------|--------|-----------|
| **Error** | Broken references, untraced tasks | 1 |
| **Warning** | Orphaned REQs, orphaned DESIGNs | 2 (pass unless -Strict) |
| **Info** | Status inconsistencies | 0 |

## Integration Points

### Pre-Commit Hook

```powershell
# .githooks/validate-traceability
scripts/Validate-Traceability.ps1 -SpecsPath ".agents/specs"
```

### CI Pipeline

```yaml
- name: Validate Traceability
  run: pwsh scripts/Validate-Traceability.ps1 -Strict
```

### Critic Agent

The critic agent includes traceability validation in its review checklist.

## Examples

### Valid Traceability Chain

```yaml
# REQ-001-feature.md
---
type: requirement
id: REQ-001
related:
  - DESIGN-001
---

# DESIGN-001-feature.md
---
type: design
id: DESIGN-001
related:
  - REQ-001
---

# TASK-001-implement.md
---
type: task
id: TASK-001
related:
  - DESIGN-001
---
```

### Orphaned Requirement (Violation)

```yaml
# REQ-002-orphan.md
---
type: requirement
id: REQ-002
related: []  # No DESIGN references this
---
```

### Broken Reference (Violation)

```yaml
# TASK-002-broken.md
---
type: task
id: TASK-002
related:
  - DESIGN-999  # Does not exist
---
```
