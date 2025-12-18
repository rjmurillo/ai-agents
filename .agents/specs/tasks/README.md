# Tasks Directory

## Purpose

This directory contains atomic task breakdowns that define **IMPLEMENTATION** units.

## Scope

Task documents break designs into small, implementable units with:

- Clear scope boundaries
- Acceptance criteria
- Complexity estimates
- File impact analysis

## File Naming

Pattern: `TASK-NNN-[kebab-case-name].md`

Examples:
- `TASK-001-implement-token-endpoint.md`
- `TASK-002-add-pkce-validation.md`
- `TASK-003-create-refresh-logic.md`

## File Structure

```yaml
---
type: task
id: TASK-NNN
status: todo | in-progress | blocked | done
priority: P0 | P1 | P2
complexity: XS | S | M | L | XL
estimate: [hours or story points]
related:
  - DESIGN-NNN (traces back)
assignee: [agent or user]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# TASK-NNN: [Task Name]

## Design Context

- DESIGN-NNN: [Brief description]

## Objective

[What this task accomplishes]

## Scope

### In Scope
- [ ] Item 1
- [ ] Item 2

### Out of Scope
- Item 1 (deferred to TASK-XXX)
- Item 2 (not required)

## Acceptance Criteria

- [ ] Criterion 1 (testable)
- [ ] Criterion 2 (testable)
- [ ] Test coverage ≥ 80%

## Implementation Notes

[Guidance for implementer]

## Files Affected

- `path/to/file1.cs` (new)
- `path/to/file2.cs` (modify)
- `path/to/file3.cs` (delete)

## Dependencies

- Blocked by: TASK-XXX (if applicable)
- Blocks: TASK-YYY (if applicable)

## Testing Strategy

[How to test this task]

## Related Documents

- Design: `specs/design/DESIGN-NNN-*.md`
- Requirements: `specs/requirements/REQ-NNN-*.md`
```

## Complexity Estimates

| Size | Hours | Story Points | Description |
|------|-------|--------------|-------------|
| XS | 1-2 | 1 | Trivial change, minimal risk |
| S | 2-4 | 2-3 | Simple change, well-understood |
| M | 4-8 | 5 | Moderate complexity, some unknowns |
| L | 8-16 | 8 | Complex change, multiple files |
| XL | 16+ | 13 | Very complex, consider splitting |

## Example

```markdown
---
type: task
id: TASK-001
status: todo
priority: P0
complexity: M
estimate: 6 hours
related:
  - DESIGN-001
created: 2025-12-18
---

# TASK-001: Implement Token Endpoint

## Design Context

- DESIGN-001: OAuth2 Authentication Flow

## Objective

Implement the `/oauth/token` endpoint that exchanges authorization codes for access and refresh tokens with PKCE validation.

## Scope

### In Scope
- [ ] Create TokenController with /oauth/token endpoint
- [ ] Validate authorization code
- [ ] Verify PKCE code verifier
- [ ] Generate access and refresh tokens
- [ ] Return token response (access_token, refresh_token, expires_in)

### Out of Scope
- Token refresh logic (deferred to TASK-002)
- Token revocation (deferred to TASK-003)

## Acceptance Criteria

- [ ] Endpoint returns 200 with tokens on valid request
- [ ] Endpoint returns 400 on invalid code
- [ ] Endpoint returns 400 on PKCE verification failure
- [ ] Access token is valid JWT with correct claims
- [ ] Refresh token is securely generated and stored
- [ ] Unit test coverage ≥ 90%
- [ ] Integration test covers happy path

## Implementation Notes

- Use existing JwtService for token generation
- Store authorization codes in IAuthorizationCodeStore
- Store refresh tokens in IRefreshTokenStore
- Validate PKCE using SHA256 hash comparison

## Files Affected

- `src/Auth/Controllers/TokenController.cs` (new)
- `src/Auth/Services/TokenService.cs` (new)
- `src/Auth/Models/TokenRequest.cs` (new)
- `src/Auth/Models/TokenResponse.cs` (new)
- `tests/Auth.Tests/Controllers/TokenControllerTests.cs` (new)

## Dependencies

- No blockers
- Blocks: TASK-002 (refresh logic needs token endpoint)

## Testing Strategy

### Unit Tests
- Valid token request returns tokens
- Invalid code returns 400
- PKCE mismatch returns 400
- Token structure validation

### Integration Tests
- Full OAuth flow from code to token
- Error scenarios (expired code, replay attack)
```

## Validation

Tasks are validated for:

1. **Atomicity**: Single, focused objective
2. **Completeness**: All sections filled
3. **Testability**: Acceptance criteria are measurable
4. **Traceability**: Links back to design
5. **Size**: XL tasks flagged for splitting

## Related Documents

- [Spec Layer Overview](../README.md)
- [Naming Conventions](../../governance/naming-conventions.md)
- [Task Generator Agent](../../../src/claude/task-generator.md)

---

*Version: 1.0*
*Created: 2025-12-18*
