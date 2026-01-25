# EARS Requirements Format

> **Version**: 1.0.0
> **Created**: 2025-12-30
> **Status**: Active
> **References**: [enhancement-PROJECT-PLAN.md](../planning/enhancement-PROJECT-PLAN.md)

## Overview

EARS (Easy Approach to Requirements Syntax) is a structured syntax for writing testable, unambiguous requirements. This document defines the EARS format used in the ai-agents specification layer.

## Why EARS?

Traditional requirements often suffer from:

- Ambiguity ("the system should be fast")
- Missing testability ("handle errors gracefully")
- Unclear triggers ("when appropriate")

EARS solves these by enforcing a consistent syntax that makes requirements:

- **Testable**: Clear acceptance criteria
- **Unambiguous**: Specific language patterns
- **Traceable**: Explicit triggers and rationale

## Basic Syntax

```text
WHEN [precondition/trigger]
THE SYSTEM SHALL [action/behavior]
SO THAT [rationale/value]
```

### Components

| Component | Purpose | Example |
|-----------|---------|---------|
| **WHEN** | Precondition or trigger | "the user submits a PR" |
| **THE SYSTEM SHALL** | Required behavior | "validate all required fields" |
| **SO THAT** | Business rationale | "incomplete PRs are rejected early" |

## EARS Patterns

### 1. Ubiquitous Requirements

Requirements that apply at all times without a specific trigger.

**Syntax**:

```text
THE SYSTEM SHALL [action]
SO THAT [rationale]
```

**Example**:

```text
THE SYSTEM SHALL use PowerShell for all scripting
SO THAT the codebase maintains language consistency per ADR-005
```

### 2. Event-Driven Requirements

Requirements triggered by a specific event.

**Syntax**:

```text
WHEN [event occurs]
THE SYSTEM SHALL [action]
SO THAT [rationale]
```

**Example**:

```text
WHEN a PR is opened
THE SYSTEM SHALL assign the AI Quality Gate workflow
SO THAT all PRs receive automated security and quality review
```

### 3. State-Driven Requirements

Requirements that apply while a condition is true.

**Syntax**:

```text
WHILE [condition is true]
THE SYSTEM SHALL [action]
SO THAT [rationale]
```

**Example**:

```text
WHILE a session is in WORKING phase
THE SYSTEM SHALL prevent phase regression to INIT
SO THAT session state machine integrity is maintained
```

### 4. Optional Feature Requirements

Requirements for optional/configurable features.

**Syntax**:

```text
WHERE [feature is enabled/configured]
THE SYSTEM SHALL [action]
SO THAT [rationale]
```

**Example**:

```text
WHERE parallel execution is enabled
THE SYSTEM SHALL dispatch tasks to multiple agents concurrently
SO THAT execution time is reduced by 2-4x
```

### 5. Unwanted Behavior Requirements

Requirements that prevent specific behaviors.

**Syntax**:

```text
IF [unwanted condition]
THEN THE SYSTEM SHALL [preventive action]
SO THAT [rationale]
```

**Example**:

```text
IF a skill script exists for a GitHub operation
THEN THE SYSTEM SHALL block raw gh commands
SO THAT skill-usage-mandatory violations are prevented
```

### 6. Complex Requirements

Requirements combining multiple conditions.

**Syntax**:

```text
WHEN [trigger]
AND [additional condition]
THE SYSTEM SHALL [action]
UNLESS [exception]
SO THAT [rationale]
```

**Example**:

```text
WHEN a session ends
AND all BLOCKING gates have passed
THE SYSTEM SHALL commit changes automatically
UNLESS the user has disabled auto-commit
SO THAT session protocol compliance is enforced
```

## YAML Front Matter Schema

All requirement documents MUST include YAML front matter:

```yaml
---
type: requirement
id: REQ-001
title: Short descriptive title
status: draft | review | approved | implemented
priority: P0 | P1 | P2
category: functional | non-functional | constraint
related:
  - REQ-000  # Parent or related requirements
  - DESIGN-001  # Linked design docs
created: YYYY-MM-DD
updated: YYYY-MM-DD
author: agent-name or human
---
```

### Field Definitions

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Always `requirement` |
| `id` | Yes | Unique identifier (REQ-NNN) |
| `title` | Yes | Brief descriptive title |
| `status` | Yes | Current lifecycle status |
| `priority` | Yes | P0 (critical), P1 (high), P2 (normal) |
| `category` | Yes | Requirement category |
| `related` | No | Links to related artifacts |
| `created` | Yes | Creation date |
| `updated` | Yes | Last modification date |
| `author` | No | Creator of the requirement |

### Status Transitions

```text
draft → review → approved → implemented
                    ↓
                rejected (terminal)
```

## Writing Guidelines

### DO

- Use active voice ("THE SYSTEM SHALL validate" not "validation shall be performed")
- Be specific about quantities ("within 500ms" not "quickly")
- Include measurable criteria ("≥80% coverage" not "good coverage")
- Reference existing artifacts (ADRs, memories, specs)

### DO NOT

- Use vague terms ("appropriate", "reasonable", "user-friendly")
- Include implementation details (that's for design docs)
- Combine multiple requirements in one statement
- Use passive voice or ambiguous subjects

## Examples

### Functional Requirement

```yaml
---
type: requirement
id: REQ-001
title: Session State Persistence
status: approved
priority: P0
category: functional
related:
  - ADR-011
created: 2025-12-30
updated: 2025-12-30
---
```

```text
WHEN a session phase transition occurs
THE SYSTEM SHALL persist the new state to Serena memory within 1 second
SO THAT session state survives MCP restarts and can be recovered
```

### Non-Functional Requirement

```yaml
---
type: requirement
id: REQ-002
title: Skill Search Performance
status: approved
priority: P1
category: non-functional
related:
  - ADR-012
created: 2025-12-30
updated: 2025-12-30
---
```

```text
THE SYSTEM SHALL return skill search results within 500ms for catalogs up to 100 skills
SO THAT agent workflows are not blocked by skill discovery
```

### Constraint Requirement

```yaml
---
type: requirement
id: REQ-003
title: PowerShell-Only Scripting
status: implemented
priority: P0
category: constraint
related:
  - ADR-005
created: 2025-12-30
updated: 2025-12-30
---
```

```text
THE SYSTEM SHALL use PowerShell (.ps1, .psm1) for all executable scripts
SO THAT the codebase maintains cross-platform consistency and testability
```

## Traceability

Every requirement MUST be traceable:

1. **Upstream**: Links to business goals, epics, or user stories
2. **Downstream**: Links to design documents and tasks
3. **Lateral**: Links to related requirements

```text
Business Goal
    ↓
[REQ-001] Requirement
    ↓
[DESIGN-001] Design Document
    ↓
[TASK-001] Implementation Task
```

## Validation

Requirements are validated by the critic agent using this checklist:

- [ ] Uses correct EARS pattern syntax
- [ ] Has complete YAML front matter
- [ ] Contains measurable/testable criteria
- [ ] Avoids vague terminology
- [ ] Links to related artifacts
- [ ] Single requirement per document (atomic)

## References

- [enhancement-PROJECT-PLAN.md](../planning/enhancement-PROJECT-PLAN.md) - Phase 1: Spec Layer
- [AGENT-SYSTEM.md](../AGENT-SYSTEM.md) - Agent architecture
- [ADR-011](../architecture/ADR-011-session-state-mcp.md) - Session State MCP
- [ADR-012](../architecture/ADR-012-skill-catalog-mcp.md) - Skill Catalog MCP
- Original EARS paper: Mavin et al., "Easy Approach to Requirements Syntax (EARS)"
