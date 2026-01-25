# Artifact Naming Conventions

## Purpose

This document defines the canonical naming patterns for all agent-generated artifacts. Consistent naming enables automated validation, cross-referencing, and traceability across the agent system.

---

## Sequenced Artifact Patterns

These artifacts use sequential numbering for uniqueness and ordering.

### EPIC-NNN Pattern

**Used by**: roadmap agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `EPIC-NNN-[kebab-case-name].md` | `EPIC-001-user-authentication.md` |
| Reference | `EPIC-NNN` | `EPIC-001` |
| Location | `.agents/roadmap/` | `.agents/roadmap/EPIC-001-user-authentication.md` |

**Numbering Rules:**

1. Numbers assigned sequentially (001, 002, 003...)
2. Numbers are NEVER reused after retirement/rejection
3. Gaps in sequence are acceptable
4. Always use 3-digit zero-padding

### ADR-NNN Pattern

**Used by**: architect agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `ADR-NNN-[kebab-case-title].md` | `ADR-005-use-pkce-for-oauth.md` |
| Reference | `ADR-NNN` | `ADR-005` |
| Location | `.agents/architecture/` | `.agents/architecture/ADR-005-use-pkce-for-oauth.md` |

**Numbering Rules:**

1. Same as EPIC-NNN (sequential, no reuse, gaps OK, 3-digit padding)
2. ADR numbers are global across the project (not per-feature)

### TM-NNN Pattern (Threat Models)

**Used by**: security agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `TM-NNN-[kebab-case-scope].md` | `TM-001-authentication-flow.md` |
| Reference | `TM-NNN` | `TM-001` |
| Location | `.agents/security/` | `.agents/security/TM-001-authentication-flow.md` |

**Numbering Rules:**

1. Same as EPIC-NNN (sequential, no reuse, gaps OK, 3-digit padding)

### Plan-NNN Pattern

**Used by**: planner agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `NNN-[kebab-case-name]-plan.md` | `001-authentication-plan.md` |
| Reference | `Plan-NNN` | `Plan-001` |
| Location | `.agents/planning/` | `.agents/planning/001-authentication-plan.md` |

**Numbering Rules:**

1. Same as EPIC-NNN (sequential, no reuse, gaps OK, 3-digit padding)

### Critique-NNN Pattern

**Used by**: critic agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `NNN-[kebab-case-name]-critique.md` | `001-authentication-critique.md` |
| Reference | `Critique-NNN` | `Critique-001` |
| Location | `.agents/critique/` | `.agents/critique/001-authentication-critique.md` |

**Numbering Rules:**

1. Numbers typically match the plan being critiqued
2. Multiple critiques of same plan use suffixes: `001a`, `001b`

### REQ-NNN Pattern (Requirements)

**Used by**: spec-generator agent (Phase 1+)

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `REQ-NNN-[kebab-case-name].md` | `REQ-001-user-authentication.md` |
| Reference | `REQ-NNN` | `REQ-001` |
| Location | `.agents/specs/requirements/` | `.agents/specs/requirements/REQ-001-user-authentication.md` |

**Numbering Rules:**

1. Same as EPIC-NNN (sequential, no reuse, gaps OK, 3-digit padding)
2. REQ numbers are global across the project

**Format**: EARS (Easy Approach to Requirements Syntax) - WHEN/SHALL/SO THAT

### DESIGN-NNN Pattern

**Used by**: architect agent (for spec layer)

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `DESIGN-NNN-[kebab-case-name].md` | `DESIGN-001-oauth2-flow.md` |
| Reference | `DESIGN-NNN` | `DESIGN-001` |
| Location | `.agents/specs/design/` | `.agents/specs/design/DESIGN-001-oauth2-flow.md` |

**Numbering Rules:**

1. Same as EPIC-NNN (sequential, no reuse, gaps OK, 3-digit padding)
2. DESIGN numbers are global across the project

### TASK-NNN Pattern

**Used by**: task-generator agent (for spec layer)

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `TASK-NNN-[kebab-case-name].md` | `TASK-001-implement-token-endpoint.md` |
| Reference | `TASK-NNN` | `TASK-001` |
| Location | `.agents/specs/tasks/` | `.agents/specs/tasks/TASK-001-implement-token-endpoint.md` |

**Numbering Rules:**

1. Same as EPIC-NNN (sequential, no reuse, gaps OK, 3-digit padding)
2. TASK numbers are global across the project

---

## Type-Prefixed Patterns

These artifacts use type prefixes for categorization without sequential numbering.

### PRD Pattern

**Used by**: explainer agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `prd-[kebab-case-name].md` | `prd-user-authentication.md` |
| Location | `.agents/planning/` | `.agents/planning/prd-user-authentication.md` |

### Tasks Pattern

**Used by**: task-generator agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `tasks-[kebab-case-name].md` | `tasks-user-authentication.md` |
| Location | `.agents/planning/` | `.agents/planning/tasks-user-authentication.md` |

### Implementation Plan Pattern

**Used by**: planner agent (during ideation workflow)

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `implementation-plan-[kebab-case-name].md` | `implementation-plan-user-authentication.md` |
| Location | `.agents/planning/` | `.agents/planning/implementation-plan-user-authentication.md` |

### Impact Analysis Pattern

**Used by**: specialist agents during impact analysis

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `impact-analysis-[domain]-[feature].md` | `impact-analysis-security-oauth.md` |
| Location | `.agents/planning/` | `.agents/planning/impact-analysis-security-oauth.md` |

### Handoff Pattern

**Used by**: orchestrator for session continuity

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `handoff-[kebab-case-topic].md` | `handoff-oauth-migration.md` |
| Location | `.agents/planning/` | `.agents/planning/handoff-oauth-migration.md` |

### Test Report Pattern

**Used by**: qa agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `NNN-[kebab-case-name]-test-report.md` | `001-authentication-test-report.md` |
| Location | `.agents/qa/` | `.agents/qa/001-authentication-test-report.md` |

### Retrospective Pattern

**Used by**: retrospective agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `YYYY-MM-DD-[kebab-case-topic].md` | `2025-01-15-authentication-sprint.md` |
| Location | `.agents/retrospective/` | `.agents/retrospective/2025-01-15-authentication-sprint.md` |

### Skill Pattern

**Used by**: skillbook agent

| Element | Format | Example |
|---------|--------|---------|
| Pattern | `Skill-[Category]-NNN.md` | `Skill-Build-001.md` |
| Reference | `Skill-[Category]-NNN` | `Skill-Build-001` |
| Location | `.agents/skills/` | `.agents/skills/Skill-Build-001.md` |

---

## Memory Entity Naming

Memory entities follow patterns defined in `memory.md`:

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `Feature-[PascalCase]` | `Feature-Authentication` |
| Module | `Module-[PascalCase]` | `Module-Identity` |
| Decision | `ADR-[Number]` | `ADR-001` |
| Pattern | `Pattern-[PascalCase]` | `Pattern-StrategyTax` |
| Problem | `Problem-[PascalCase]` | `Problem-CachingRace` |
| Solution | `Solution-[PascalCase]` | `Solution-LockingCache` |
| Skill | `Skill-[Category]-[Number]` | `Skill-Build-001` |

---

## Cross-Reference Format

When referencing artifacts across documents:

**Within `.agents/` directory** (use relative paths from `.agents/` root):

```markdown
- Epic: `roadmap/EPIC-001-user-authentication.md`
- ADR: `architecture/ADR-005-use-pkce-for-oauth.md`
- PRD: `planning/prd-user-authentication.md`
```

**From `src/` directory** (use relative paths from repo root):

```markdown
- Governance: `.agents/governance/naming-conventions.md`
- Epic: `.agents/roadmap/EPIC-001-user-authentication.md`
```

---

## Validation Rules

Automated validation should check:

1. **Format Compliance**: File names match declared patterns
2. **Number Uniqueness**: No duplicate NNN values within a category
3. **Path Correctness**: Files exist at declared locations
4. **Reference Validity**: Cross-references point to existing files
5. **Case Consistency**: kebab-case for file names, PascalCase for entities

### Validation Script Location

See `.agents/utilities/validate-naming.ps1` (to be created if needed)

---

## Related Documents

- [Agent Design Principles](./agent-design-principles.md) - Principle 6: Consistent Interface
- [Consistency Protocol](./consistency-protocol.md) - Cross-document validation
- [Memory Agent](../../src/claude/memory.md) - Entity naming conventions
- [Roadmap Agent](../../src/claude/roadmap.md) - Epic naming conventions

---

*Version: 1.0*
*Established: 2025-12-16*
*GitHub Issue: #44*
