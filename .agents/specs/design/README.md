# Design Directory

## Purpose

This directory contains design documents that define **HOW** the system will fulfill requirements.

## Scope

Design documents bridge requirements and implementation, providing:

- Architecture decisions
- Component interactions
- Data flow diagrams
- API contracts
- Technology choices

## File Naming

Pattern: `DESIGN-NNN-[kebab-case-name].md`

Examples:
- `DESIGN-001-oauth2-flow.md`
- `DESIGN-002-token-storage.md`
- `DESIGN-003-password-hashing.md`

## File Structure

```yaml
---
type: design
id: DESIGN-NNN
status: draft | review | approved | implemented
priority: P0 | P1 | P2
related:
  - REQ-NNN (traces back)
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# DESIGN-NNN: [Design Name]

## Requirements Addressed

- REQ-NNN: [Brief description]

## Design Overview

[High-level approach]

## Component Details

### Component 1
[Details]

### Component 2
[Details]

## Data Flow

[Diagram or description]

## API Contracts

[If applicable]

## Technology Decisions

- **Choice**: [Technology/pattern]
- **Rationale**: [Why this choice]
- **Alternatives Considered**: [Other options]

## Security Considerations

[Security-relevant design aspects]

## Performance Considerations

[Performance-relevant design aspects]

## Testing Strategy

[How this design will be tested]

## Related Documents

- Requirements: `specs/requirements/REQ-NNN-*.md`
- Tasks: `specs/tasks/TASK-NNN-*.md` (traces forward)
- ADRs: `architecture/ADR-NNN-*.md` (if applicable)
```

## Example

```markdown
---
type: design
id: DESIGN-001
status: approved
priority: P0
related:
  - REQ-001
  - REQ-002
created: 2025-12-18
---

# DESIGN-001: OAuth2 Authentication Flow

## Requirements Addressed

- REQ-001: User login with credential validation
- REQ-002: Token refresh mechanism

## Design Overview

Implement OAuth2 authorization code flow with PKCE for enhanced security.

## Component Details

### Authorization Server
- Endpoint: `/oauth/authorize`
- Validates client credentials
- Issues authorization codes

### Token Endpoint
- Endpoint: `/oauth/token`
- Exchanges auth code for access/refresh tokens
- Validates PKCE code verifier

### Resource Server
- Validates JWT tokens
- Enforces scope-based access control

## Data Flow

1. Client initiates auth request with PKCE challenge
2. User authenticates
3. Server issues authorization code
4. Client exchanges code + verifier for tokens
5. Client uses access token for API calls

## Technology Decisions

- **JWT**: Self-contained tokens for stateless validation
- **PKCE**: Protection against authorization code interception
- **HS256**: Symmetric signing for internal services

## Security Considerations

- Code challenge prevents authorization code interception
- Token rotation on refresh
- Refresh tokens stored securely in httpOnly cookies

## Testing Strategy

- Unit tests for token generation/validation
- Integration tests for full OAuth flow
- Security tests for common attacks (CSRF, token theft)
```

## Validation

Design documents are validated for:

1. **Requirements Coverage**: Must address at least one REQ-NNN
2. **Completeness**: All sections filled appropriately
3. **Traceability**: Must link back to requirements, forward to tasks
4. **Technical Clarity**: Design must be implementable

## Related Documents

- [Spec Layer Overview](../README.md)
- [Naming Conventions](../../governance/naming-conventions.md)
- [Architecture ADRs](../../architecture/)

---

*Version: 1.0*
*Created: 2025-12-18*
