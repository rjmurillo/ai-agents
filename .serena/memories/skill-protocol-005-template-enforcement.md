# Skill-Protocol-005: Template Enforcement

## Statement

Require exact copy of SESSION-PROTOCOL.md checklist template; custom formats prevent automated validation

## Context

When creating session logs at `.agents/sessions/YYYY-MM-DD-session-NN.md`

## Evidence

**Session-46 (2025-12-20)**: Created custom "Session End Requirements" format claiming `[COMPLETE]` but failed validation script (format mismatch)

**Mass failure (2025-12-20)**: 6+ sessions created ad-hoc formats instead of canonical template from SESSION-PROTOCOL.md lines 300-313

**Validation impact**: Scripts cannot parse arbitrary formats - regex pattern matching requires standardized structure

## Metrics

- **Atomicity**: 94%
- **Impact**: 9/10
- **Category**: protocol, template, validation
- **Created**: 2025-12-20
- **Tag**: helpful
- **Validated**: 1 (24-session analysis)

## Pattern

### CORRECT: Exact Template Copy

```markdown
## Session End (COMPLETE ALL before closing)

Protocol Compliance:
- [x] Session Start protocol (Phase 1 & 2) completed
- [x] Serena initialized via mcp__serena__activate_project
- [x] Serena instructions read via mcp__serena__initial_instructions
- [x] HANDOFF.md read for context

Session End Requirements:
- [x] Retrospective assessment: [Not merited / Completed at ...]
- [x] Update HANDOFF.md with session summary
- [x] Run `npx markdownlint-cli2 --fix "**/*.md"`
- [x] Commit all changes including .agents/ files

Commit SHA: [abc123d]
```

### INCORRECT: Custom Format

```markdown
## Session End Requirements
- [COMPLETE] Retrospective assessment: Not merited
- [COMPLETE] Update HANDOFF.md
- [COMPLETE] Run markdown lint
- [COMPLETE] Commit changes (commit 3b6559d)
```

## Verification

```powershell
# Check session log uses canonical format
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/2025-12-20-session-46.md"
# FAIL: Custom format not parseable
```

## Related Skills

- Skill-Protocol-002 (Verification-Based Gate Effectiveness)
- Skill-Git-001 (Pre-Commit Validation)
- Skill-Logging-002 (Session Log Early Creation)

## Row Count Requirement

Session End checklist MUST have exactly 8 rows (5 MUST + 3 SHOULD):

| Row Type | Count | Description |
|----------|-------|-------------|
| Protocol Compliance (MUST) | 4 | Serena init, instructions, HANDOFF read, session start |
| Session End (MUST) | 1 | Retrospective assessment |
| Deliverables (SHOULD) | 3 | HANDOFF update, lint, commit |
| **Total** | **8** | **Enforced by validator** |

Using different row count triggers E_TEMPLATE_DRIFT error.

Reference: Skill-Protocol-007 (Session End Checklist Row Count Enforcement)

## Source

- `.agents/retrospective/2025-12-20-session-protocol-mass-failure.md` (Learning 2, lines 660-678)
- `.agents/skills/pr143-session-validation-merge-commits.md` (Skill-Protocol-007)
