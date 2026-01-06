# Session-Init-Pattern: Verification-Based Session Creation

**Statement**: Use `/session-init` skill to create session logs with immediate validation.

**Context**: Prevents recurring CI validation failures caused by malformed session logs.

**Evidence**: Follows proven Serena initialization pattern (verification-based enforcement).

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Eliminates 1-2 turn remediation latency on every PR

**Pattern**: Verification-based enforcement (template read from file + immediate validation)

## The Problem

Every PR starts with malformed session logs that fail CI validation due to missing text in the "Session End" header. The template requires `### Session End (COMPLETE ALL before closing)` but agents write `## Session End`.

**Root Cause**: Agents generate session logs from LLM memory instead of copying the canonical template from SESSION-PROTOCOL.md.

## The Solution

Use the `/session-init` skill which:

1. Reads canonical template from SESSION-PROTOCOL.md (lines 494-612)
2. Prompts for session number and objective
3. Auto-populates git state (branch, commit, date)
4. Writes session log with EXACT template format
5. Validates immediately with Validate-SessionProtocol.ps1

## Why It Works

- Reads canonical template from file (single source of truth)
- Auto-populates git state (reduces manual errors)
- Validates immediately with same script as CI (instant feedback)
- Cannot skip validation (built into skill workflow)
- Provides actionable error messages if validation fails

## Comparison to Serena Init

| Aspect | Serena Init | Session Init |
|--------|-------------|--------------|
| Verification | Tool output in transcript | Validation script exit code |
| Feedback | Immediate (tool response) | Immediate (validation output) |
| Enforcement | Cannot proceed without output | Cannot claim success without pass |
| Compliance Rate | 100% (never violated) | Target: 100% |

## Triggers

- `/session-init` - Explicit invocation
- `create session log` - Natural language
- `start new session` - Alternative

## Related

- `.claude/skills/session-init/SKILL.md` - Skill documentation
- `.claude/skills/session-log-fixer/SKILL.md` - Reactive fix (use session-init instead)
- `.agents/SESSION-PROTOCOL.md` - Canonical template source (lines 494-612)
- `scripts/Validate-SessionProtocol.ps1` - Validation script
