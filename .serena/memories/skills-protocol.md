# Protocol Skills

**Created**: 2025-12-23 (consolidated from 4 atomic memories)
**Sources**: SESSION-PROTOCOL.md retrospectives, PR reviews
**Skills**: 4

---

## Skill-Protocol-001: Verification-Based BLOCKING Gates

**Statement**: Verification-based BLOCKING gates (tool output required) achieve 100% compliance where trust-based guidance fails

**Context**: When adding new protocol requirements to SESSION-PROTOCOL.md

**Evidence**: Phase 1 Serena init has BLOCKING gate → 100% compliance. Trust-based guidance had 5+ violations.

**Atomicity**: 100% | **Impact**: 10/10 | **Tag**: critical

**Gate Design Template**:

```markdown
## Phase X: [Name] (BLOCKING)

You MUST [action] before [next step]:

1. [Required action 1]
2. [Required action 2]

**Verification**: [How to verify - tool output, file exists, etc.]

**If skipped**: [Consequence - context lost, errors, etc.]
```

**Required Elements**:
1. BLOCKING keyword
2. MUST language (RFC 2119)
3. Verification method
4. Tool output evidence in transcript
5. Clear consequence if skipped

**Comparison**:

| Type | Compliance | Pattern |
|------|------------|---------|
| Verification-based BLOCKING | 100% | "MUST NOT proceed until tool output appears" |
| Trust-based guidance | <50% | "should read" / "remember to" |

---

## Skill-Protocol-002: RFC 2119 MUST Evidence

**Statement**: Implement RFC 2119 MUST requirements with verification evidence

**Context**: Any phase transition in protocol

**Evidence**: PR #147 - Agent claimed compliance without verification evidence

**Atomicity**: 96% | **Impact**: 10/10 | **Tag**: critical

**Compliance Pattern**:

1. **Execute**: Perform action via tool call
2. **Verify**: Read output/artifact to confirm success
3. **Log**: Record evidence in session log
4. **Gate**: Do not proceed without all three

**Evidence Format**:

```markdown
## Phase 3: Session Log Creation

Evidence:
- Tool: Write(.agents/sessions/2025-12-20-session-01.md)
- Verification: Read(...) - 45 lines
- Confirmed: File exists with Protocol Compliance section
```

**Anti-pattern**: Proceeding based on memory of prior action without verification

---

## Skill-Protocol-003: Template Enforcement

**Statement**: Require exact copy of SESSION-PROTOCOL.md checklist template; custom formats prevent automated validation

**Context**: When creating session logs at `.agents/sessions/`

**Evidence**: Session-46: Custom "Session End Requirements" format failed validation script

**Atomicity**: 94% | **Impact**: 9/10 | **Tag**: helpful

**CORRECT - Exact Template**:

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

**INCORRECT - Custom Format**:

```markdown
## Session End Requirements
- [COMPLETE] Update HANDOFF.md  <!-- Not parseable -->
```

**Why**: Scripts use regex pattern matching - arbitrary formats cannot be validated.

---

## Skill-Protocol-004: Legacy Session Grandfathering

**Statement**: Sessions created before SESSION-PROTOCOL.md can use LEGACY markers for compliance

**Context**: Remediating historical sessions or adding pre-2025-12-21 sessions to PRs

**Evidence**: PR #53: Session-41 blocked merge - added LEGACY markers, validator passed

**Atomicity**: 95% | **Impact**: 8/10 | **Tag**: helpful

**LEGACY Format**:

```markdown
## Protocol Compliance

### Phase 1: Serena Initialization [LEGACY]

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena | [x] | LEGACY: Predates protocol template |

> **Note**: This session was created on [DATE] before SESSION-PROTOCOL.md v2.0.
```

**When to Apply**:
- Session created before 2025-12-21
- Session lacks Protocol Compliance section
- Session uses non-canonical format
- Session blocks CI in PR

---

## Quick Reference

| Skill | When to Use |
|-------|-------------|
| 001 | Adding protocol requirements - use BLOCKING gates |
| 002 | Phase transitions - log verification evidence |
| 003 | Creating session logs - use exact template |
| 004 | Historical sessions - use LEGACY markers |

## Related

- SESSION-PROTOCOL.md (canonical protocol)
- Validate-SessionEnd.ps1 (validation script)
- skills-orchestration (Skill-Orchestration-003 handoff validation)
