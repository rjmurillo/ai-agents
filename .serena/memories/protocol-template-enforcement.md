# Skill-Protocol-003: Template Enforcement via session-init

**Statement**: Agents MUST use session-init skill to enforce exact copy of SESSION-PROTOCOL.md checklist template; custom formats prevent automated validation

**Context**: When creating session logs at `.agents/sessions/` - use `/session-init` skill for verification-based enforcement

**Evidence**: Session-46: Custom "Session End Requirements" format failed validation script. Session-374 RCA: 10+ recurring fixes for same validation issue. Git history: `510ac258`, `b8debe43`, `8cc373c0`, `6f171473`, `2f5545b2`

**Atomicity**: 94%

**Impact**: 9/10

**Tag**: CRITICAL

## Canonical Template Enforcement

The session-init skill provides verification-based enforcement:

1. **Reads canonical template** from SESSION-PROTOCOL.md (lines 494-612) using regex extraction
2. **Populates placeholders** with git state (branch, commit, date, status)
3. **Writes session log** with EXACT template format
4. **Validates immediately** with Validate-SessionProtocol.ps1
5. **Exits nonzero** on validation failure

This ensures agents CANNOT create malformed session logs at source.

## CORRECT - session-init Generated

```markdown
### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Session log created early | [ ] | This file being created now |
| MUST | Work completed | [ ] | Implementation complete |
| MUST | HANDOFF.md NOT updated | [ ] | Read-only, not modified |
| MUST | Markdown lint run | [ ] | npx markdownlint-cli2 --fix "**/*.md" |
| MUST | All changes committed | [ ] | Commit SHA: [commit] |
| MUST | Serena memory updated | [ ] | Memory write confirmed |
| MUST | Run session validation | [ ] | pwsh scripts/Validate-SessionProtocol.ps1 -SessionLogPath [path] |
```

## INCORRECT - LLM Generated

```markdown
## Session End

- [COMPLETE] Update HANDOFF.md  <!-- Not parseable -->
- [x] Run linting                <!-- Missing table structure -->
```

**Problems**:

- Wrong header level (`##` vs `###`)
- Missing required text "(COMPLETE ALL before closing)"
- Non-standard format (not parseable by validation script)
- Custom checkbox syntax not recognized

## Why session-init Works

- **Regex-based extraction**: Resilient to line number changes in SESSION-PROTOCOL.md
- **Single source of truth**: Template read from file, not LLM memory
- **Immediate validation**: Same script as CI, instant feedback
- **Cannot skip**: Validation built into skill workflow
- **Deterministic naming**: Generates human-readable filenames with keywords from objective

## Session Naming Convention

**Format**: `YYYY-MM-DD-session-NN-keyword1-keyword2-keyword3-keyword4-keyword5.md`

**Extraction Logic**:

1. Extract 5 most relevant keywords from session objective
2. Convert to kebab-case
3. Append to standard date-session-number prefix

**Examples**:

| Objective | Filename |
|-----------|----------|
| "Debug recurring session validation failures" | `2026-01-06-session-374-debug-recurring-session-validation-failures.md` |
| "Implement OAuth 2.0 authentication" | `2026-01-06-session-375-implement-oauth-authentication.md` |

**Benefits**: Human-readable session discovery, grep-friendly search, self-documenting filenames

## Enforcement Level

**RFC 2119**: MUST (mandatory, not optional)

Agents MUST use `/session-init` skill. Manual session creation is prohibited due to recurring validation failures.

## Related

- `.claude/skills/session-init/SKILL.md` - Skill documentation with 5-phase workflow
- `.claude/commands/session-init.md` - Slash command for deterministic invocation
- `.serena/memories/session-init-pattern.md` - Verification-based enforcement pattern
- `.agents/SESSION-PROTOCOL.md` - Canonical template source (lines 494-612)
- scripts/Validate-SessionProtocol.ps1 (removed) - Validation script used by CI and skill

## Related

- [protocol-012-branch-handoffs](protocol-012-branch-handoffs.md)
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [protocol-continuation-session-gap](protocol-continuation-session-gap.md)
