# Skill-Init-001: Serena Mandatory Initialization

**Statement**: MUST initialize Serena with `mcp__serena__activate_project` and `mcp__serena__initial_instructions` before ANY other action.

**Context**: BLOCKING gate at session start (Phase 1 of SESSION-PROTOCOL.md)

**Evidence**: This gate works perfectly - never violated in any session.

**Atomicity**: 98%

**Tag**: CRITICAL

**Impact**: 10/10 - Enables semantic code tools and project memories

**Pattern**: Verification-based enforcement (tool output required in transcript)

## Why It Works

- Gate requires tool OUTPUT (not promise)
- Visible in session transcript
- Cannot be skipped without detection
- Provides immediate feedback if missed

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
