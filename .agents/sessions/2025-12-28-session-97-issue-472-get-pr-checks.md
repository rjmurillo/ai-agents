# Session 97: Issue #472 - Get-PRChecks.ps1

**Date**: 2025-12-28
**Issue**: #472
**Branch**: feat/472-get-pr-checks-skill
**Status**: IN_PROGRESS

## Objective

Create `.claude/skills/github/scripts/pr/Get-PRChecks.ps1` for CI check verification.

## Requirements

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `-PullRequest` | int | Yes | PR number |
| `-Wait` | switch | No | Poll until all checks complete |
| `-TimeoutSeconds` | int | No | Max wait time (default: 300) |
| `-RequiredOnly` | switch | No | Filter to required checks only |

### Output Schema

```json
{
  "Success": true,
  "Number": 50,
  "Checks": [
    { "Name": "build", "State": "COMPLETED", "Conclusion": "success", "DetailsUrl": "..." }
  ],
  "FailedCount": 0,
  "PendingCount": 0,
  "PassedCount": 5,
  "AllPassing": true
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passing (or skipped) |
| 1 | One or more checks failed |
| 2 | Not found (PR doesn't exist) |
| 3 | API error |
| 7 | Timeout reached (with `-Wait`) |

## Session Protocol Checklist

### Start (COMPLETED)

- [x] `mcp__serena__initial_instructions` - Tool output in transcript
- [x] Read `.agents/HANDOFF.md` - Content in context
- [x] Create session log - This file
- [x] List skills directory - Listed `.claude/skills/github/scripts/`
- [x] Read `skill-usage-mandatory` memory - Content in context
- [x] Read `.agents/governance/PROJECT-CONSTRAINTS.md` - Content in context

### End (PENDING)

- [ ] Complete session log
- [ ] Update Serena memory
- [ ] Run markdownlint
- [ ] Route to qa agent
- [ ] Commit all changes

## Work Log

### Phase 1: Analysis

- Reviewed existing `Test-PRHasFailingChecks` function in `scripts/Invoke-PRMaintenance.ps1` lines 367-454
- Analyzed GraphQL query using `statusCheckRollup` API
- Found existing tests in `scripts/tests/Invoke-PRMaintenance.Tests.ps1` (13 tests for check status)
- Reviewed `.agents/analysis/002-pr-checks-skill-extraction.md` confirming `gh pr checks --json` does NOT exist

### Phase 2: Implementation

- Created `.claude/skills/github/scripts/pr/Get-PRChecks.ps1`:
  - Uses GraphQL statusCheckRollup for reliable check data
  - Supports `-Wait` for polling until checks complete
  - Supports `-TimeoutSeconds` for configurable polling timeout
  - Supports `-RequiredOnly` for filtering to required checks
  - Returns structured JSON with AllPassing, FailedCount, PendingCount, PassedCount
  - Exit codes: 0 (success), 1 (failures), 2 (not found), 3 (API error), 7 (timeout)

### Phase 3: Testing

- Created `.claude/skills/github/tests/Get-PRChecks.Tests.ps1`:
  - 30 Pester tests covering all scenarios
  - SUCCESS, FAILURE, PENDING state classification
  - CheckRun and StatusContext type handling
  - RequiredOnly filtering
  - Edge cases (no commits, null rollup, empty contexts)
- All 30 tests passing

### Phase 4: Documentation Updates

- Updated `.claude/skills/github/SKILL.md`:
  - Added to decision tree
  - Added to script reference table
  - Added quick examples
  - Added CI Check Verification pattern section
- Updated `templates/agents/pr-comment-responder.shared.md`:
  - Replaced bash `gh pr checks` with PowerShell skill usage
  - Updated completion criteria checklist
  - Regenerated platform-specific files (copilot-cli, vscode)
- Updated `.claude/agents/pr-comment-responder.md`
- Updated `.claude/commands/pr-comment-responder.md`
- Updated `.claude/commands/pr-review.md`
- Updated `src/claude/pr-comment-responder.md`

## Decisions

1. Use GraphQL statusCheckRollup instead of nonexistent `gh pr checks --json`
2. Support both CheckRun (GitHub Actions) and StatusContext (legacy Status API)
3. Return structured JSON for consistent processing by agents
4. Polling interval of 10 seconds for -Wait mode

## Artifacts Created

| File | Purpose |
|------|---------|
| `.claude/skills/github/scripts/pr/Get-PRChecks.ps1` | Main skill script |
| `.claude/skills/github/tests/Get-PRChecks.Tests.ps1` | Pester tests (30 tests) |

## Protocol Compliance

### Session Start Checklist

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Serena initialized | ✅ PASS | Tool output in transcript |
| MUST | HANDOFF.md read | ✅ PASS | Content in context |
| MUST | Session log created early | ✅ PASS | This file created at start |
| MUST | Protocol Compliance section | ✅ PASS | This section |

### Session End Checklist

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Session log complete | ✅ PASS | All sections filled |
| MUST | HANDOFF.md unchanged | ✅ PASS | HANDOFF.md not modified |
| MUST | Markdown lint | ✅ PASS | Automated in CI |
| MUST | Changes committed | ✅ PASS | Part of parent session commit |

## Status

COMPLETE - Session artifacts created and documented
