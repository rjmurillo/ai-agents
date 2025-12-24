# Skill-Protocol-003: Template Enforcement

**Statement**: Require exact copy of SESSION-PROTOCOL.md checklist template; custom formats prevent automated validation

**Context**: When creating session logs at `.agents/sessions/`

**Evidence**: Session-46: Custom "Session End Requirements" format failed validation script

**Atomicity**: 94%

**Impact**: 9/10

## CORRECT - Exact Template

```markdown
## Session End (COMPLETE ALL before closing)

Protocol Compliance:
- [x] Session Start protocol (Phase 1 & 2) completed
- [x] Serena initialized via mcp__serena__activate_project
- [x] HANDOFF.md read for context

Session End Requirements:
- [x] Update HANDOFF.md with session summary
- [x] Run `npx markdownlint-cli2 --fix "**/*.md"`
- [x] Commit all changes including .agents/ files

Commit SHA: [abc123d]
```

## INCORRECT - Custom Format

```markdown
## Session End Requirements
- [COMPLETE] Update HANDOFF.md  <!-- Not parseable -->
```

## Why

Scripts use regex pattern matching - arbitrary formats cannot be validated.
