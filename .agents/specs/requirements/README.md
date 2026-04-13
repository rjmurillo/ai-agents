# Requirements Directory

## Purpose

This directory contains EARS-format requirements that define **WHAT** the system should do and **WHY**.

## EARS Format

EARS (Easy Approach to Requirements Syntax) enforces testable, unambiguous requirements. EARS provides five main categories plus complex combinations:

| Category | Keyword | Use When |
|----------|---------|----------|
| Ubiquitous | (none) | Always active |
| Event-driven | WHEN | Triggered by event |
| State-driven | WHILE | Active during state |
| Unwanted behavior | IF/THEN | Error handling |
| Optional feature | WHERE | Feature-dependent |
| Complex | (combined) | Multiple patterns |

See [EARS-TEMPLATE.md](./EARS-TEMPLATE.md) for complete patterns and examples for each category.

### Basic Pattern

```text
WHEN [precondition/trigger]
THE SYSTEM SHALL [action/behavior]
SO THAT [rationale/value]
```

## File Naming

Pattern: `REQ-NNN-[kebab-case-name].md`

Examples:
- `REQ-001-user-authentication.md`
- `REQ-002-token-refresh.md`
- `REQ-003-password-reset.md`

## File Structure

```yaml
---
type: requirement
id: REQ-NNN
status: draft | review | approved | implemented
priority: P0 | P1 | P2
epic: EPIC-NNN (optional)
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# REQ-NNN: [Requirement Name]

## Requirement Statement

WHEN [precondition]
THE SYSTEM SHALL [action]
SO THAT [rationale]

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Related Documents

- Epic: `roadmap/EPIC-NNN-*.md` (if applicable)
- Design: `specs/design/DESIGN-NNN-*.md` (traces forward)
```

## Examples

### Functional Requirement

```markdown
---
type: requirement
id: REQ-001
status: approved
priority: P0
created: 2025-12-18
---

# REQ-001: User Login

## Requirement Statement

WHEN a user provides valid credentials
THE SYSTEM SHALL authenticate the user and issue a session token
SO THAT the user can access protected resources

## Acceptance Criteria

- [ ] Validates username and password
- [ ] Issues JWT token on success
- [ ] Returns 401 on invalid credentials
- [ ] Logs authentication attempts
```

### Non-Functional Requirement

```markdown
---
type: requirement
id: REQ-010
status: approved
priority: P1
created: 2025-12-18
---

# REQ-010: Authentication Performance

## Requirement Statement

WHEN a user attempts to log in
THE SYSTEM SHALL respond within 200ms at the 95th percentile
SO THAT user experience remains responsive

## Acceptance Criteria

- [ ] p95 latency ≤ 200ms
- [ ] p99 latency ≤ 500ms
- [ ] Measured under 100 concurrent users
```

## Validation

Requirements are validated for:

1. **EARS Compliance**: Must follow correct pattern for category (see [EARS-TEMPLATE.md](./EARS-TEMPLATE.md))
2. **Testability**: Acceptance criteria must be measurable
3. **Traceability**: Must link to design documents
4. **Uniqueness**: No duplicate REQ-NNN IDs

## Related Documents

- [EARS Template](./EARS-TEMPLATE.md) - Complete patterns for all EARS categories
- [Spec Layer Overview](../README.md)
- [Naming Conventions](../../governance/naming-conventions.md)
- [Consistency Protocol](../../governance/consistency-protocol.md)

---

*Version: 1.1*
*Created: 2025-12-18*
*Updated: 2026-02-21*
