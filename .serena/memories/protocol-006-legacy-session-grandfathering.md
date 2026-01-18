# Skill-Protocol-006: Legacy Session Grandfathering

## Statement

Sessions created before the SESSION-PROTOCOL.md template was established can use LEGACY markers to satisfy compliance requirements they could not have known about at the time.

## Context

When remediating historical sessions or adding new sessions from before 2025-12-21 to PRs.

## Evidence

**PR #53 (2025-12-21)**: Session-41 from 2025-12-20 blocked PR merge because it lacked:
- Protocol Compliance section (not yet required)
- Serena initialization evidence (different format at the time)
- HANDOFF.md update evidence (different workflow)

**Resolution**: Added Protocol Compliance section with LEGACY markers - validator passed.

**Validator Prompt** (`.github/prompts/session-protocol-check.md`): Explicitly documents grandfathering:

```text
### LEGACY Sessions

Sessions created before the protocol was established may contain `LEGACY` markers. When you see:

- `LEGACY: Predates requirement` in the Evidence column
- `[LEGACY]` prefix in status
- References to "predates" or "historical session"

These PASS the requirement because they are grandfathered from before the protocol existed.
```

## Metrics

- **Atomicity**: 95%
- **Impact**: 8/10
- **Category**: protocol, legacy, compliance
- **Created**: 2025-12-21
- **Tag**: helpful
- **Validated**: 1 (PR #53 unblocked)

## Pattern

### Required LEGACY Format

When adding Protocol Compliance to legacy sessions, use this format:

```markdown
## Protocol Compliance

### Phase 1: Serena Initialization [LEGACY]

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | LEGACY: Predates protocol template |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [x] | LEGACY: Predates protocol template |

### Phase 2: Context Retrieval [LEGACY]

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Read `.agents/HANDOFF.md` | [x] | LEGACY: Predates protocol template |

### Phase 3: Session Log [LEGACY]

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Create this session log | [x] | LEGACY: This file exists |

> **Note**: This session was created on [DATE] before the current SESSION-PROTOCOL.md template was established.
```

### Session End Checklist Updates

For legacy sessions, update Evidence column:

```markdown
| MUST | Update `.agents/HANDOFF.md` | [x] | LEGACY: Predates protocol template |
| MUST | Run markdown lint | [x] | LEGACY: Predates protocol template |
| MUST | Commit all changes | [x] | LEGACY: Commit SHA: [sha] |
```

## When to Apply

Apply LEGACY markers when:

1. Session was created before 2025-12-21 (SESSION-PROTOCOL.md v2.0)
2. Session lacks Protocol Compliance section
3. Session uses non-canonical Session End format
4. Session is being added to a PR and blocks CI

## Related Skills

- Skill-Protocol-005 (Template Enforcement)
- Skill-Protocol-002 (Verification-Based Gate Effectiveness)

## Source

PR #53 remediation, commit 00272c3
