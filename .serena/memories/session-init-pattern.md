# Session-Init-Pattern: Verification-Based Session Creation

**Statement**: Agents MUST use `/session-init` skill to create session logs with immediate validation and deterministic naming.

**Context**: Prevents recurring CI validation failures caused by malformed session logs. Enables human-readable session discovery without opening files.

**Evidence**: Follows proven Serena initialization pattern (verification-based enforcement). Git history shows 10+ recurring fixes for same validation issue.

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Eliminates 1-2 turn remediation latency on every PR + enables session discovery via filename

**Pattern**: Verification-based enforcement (template read from file + immediate validation) + deterministic naming

## The Problem

1. **Malformed Session Logs**: Every PR starts with malformed session logs that fail CI validation due to missing text in the "Session End" header. The template requires `### Session End (COMPLETE ALL before closing)` but agents write `## Session End`.

2. **Non-Discoverable Sessions**: Generic filenames (2026-01-06-session-375.md) require opening files to understand content. No way to browse session history efficiently.

**Root Cause**: Agents generate session logs from LLM memory instead of copying the canonical template from SESSION-PROTOCOL.md. Agents use sequential numbering without descriptive context.

## The Solution

Agents MUST use the `/session-init` skill which:

1. Reads canonical template from SESSION-PROTOCOL.md (lines 494-612)
2. Prompts for session number and objective
3. Auto-populates git state (branch, commit, date)
4. Extracts 5 most relevant keywords from objective (using NLP heuristics)
5. Generates kebab-case filename descriptors from keywords
6. Writes session log with EXACT template format: `YYYY-MM-DD-session-NN-keyword1-keyword2-keyword3-keyword4-keyword5.md`
7. Validates immediately with Validate-SessionProtocol.ps1

## Descriptive Filename Protocol

**Format**: `YYYY-MM-DD-session-NN-keyword1-keyword2-keyword3-keyword4-keyword5.md`

**Examples**:

| Objective | Filename |
|-----------|----------|
| "Debug recurring session validation failures" | `2026-01-06-session-374-debug-recurring-session-validation-failures.md` |
| "Implement OAuth 2.0 authentication flow" | `2026-01-06-session-375-implement-oauth-authentication-flow.md` |
| "Fix test coverage gaps in UserService" | `2026-01-06-session-376-fix-test-coverage-gaps-userservice.md` |

**Benefits**:

- Human-readable session discovery via `ls .agents/sessions/`
- Grep-friendly session search: `grep -l "oauth" .agents/sessions/*.json`
- Self-documenting filenames eliminate need to open files
- Chronological sorting preserved (YYYY-MM-DD prefix)
- Cross-session pattern identification via keyword clustering

## Why It Works

- Reads canonical template from file (single source of truth)
- Auto-populates git state (reduces manual errors)
- Validates immediately with same script as CI (instant feedback)
- Cannot skip validation (built into skill workflow)
- Provides actionable error messages if validation fails
- Generates human-readable filenames from session objectives
- Enables cross-session memory persistence in Serena

## Comparison to Serena Init

| Aspect | Serena Init | Session Init |
|--------|-------------|--------------|
| Verification | Tool output in transcript | Validation script exit code |
| Feedback | Immediate (tool response) | Immediate (validation output) |
| Enforcement | Cannot proceed without output | Cannot claim success without pass |
| Compliance Rate | 100% (never violated) | Target: 100% |
| Naming | N/A | Deterministic with descriptive keywords |

## Triggers

- `/session-init` - Explicit invocation (RECOMMENDED)
- `create session log` - Natural language
- `start new session` - Alternative

## Related

- `.claude/skills/session-init/SKILL.md` - Skill documentation
- `.claude/commands/session-init.md` - Slash command documentation
- `.claude/skills/session-log-fixer/SKILL.md` - Reactive fix (use session-init instead)
- `.agents/SESSION-PROTOCOL.md` - Canonical template source (lines 494-612)
- `scripts/Validate-SessionProtocol.ps1` - Validation script
- `.serena/memories/protocol-template-enforcement.md` - Template enforcement pattern

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
