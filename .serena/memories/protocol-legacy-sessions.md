# Skill-Protocol-004: Legacy Session Grandfathering

**Statement**: Sessions created before SESSION-PROTOCOL.md can use LEGACY markers for compliance

**Context**: Remediating historical sessions or adding pre-2025-12-21 sessions to PRs

**Evidence**: PR #53: Session-41 blocked merge - added LEGACY markers, validator passed

**Atomicity**: 95%

**Impact**: 8/10

## LEGACY Format

```markdown
## Protocol Compliance

### Phase 1: Serena Initialization [LEGACY]

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena | [x] | LEGACY: Predates protocol template |

> **Note**: This session was created on [DATE] before SESSION-PROTOCOL.md v2.0.
```

## When to Apply

- Session created before 2025-12-21
- Session lacks Protocol Compliance section
- Session uses non-canonical format
- Session blocks CI in PR
