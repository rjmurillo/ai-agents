# Session Validation Reconciliation

## Problem Solved

47% of PRs failed CI's Session Protocol Validation because:

- Pre-commit only validated Session End requirements
- CI validated BOTH Session Start AND Session End
- Gap: Sessions passed pre-commit but failed CI

## Solution

Extended scripts/Validate-SessionEnd.ps1 (removed) to validate:

1. **Session Start** - Checks for canonical table format with MUST rows
2. **Session End** - Existing validation preserved

## Canonical Format

Only ONE format is accepted (from SESSION-PROTOCOL.md):

```markdown
### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | Tool output present |
```

Non-canonical formats (bullet lists like `- [x] item`) are NOT accepted.

## Files Updated

- scripts/Validate-SessionEnd.ps1 (removed) - Session Start validation added
- `.githooks/pre-commit` - Comments and error messages updated
- `.agents/AGENT-INSTRUCTIONS.md` - References SESSION-PROTOCOL.md (DRY)

## Session Reference

Session 104 (2025-12-30-session-104-reconcile-session-validation.md)

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
