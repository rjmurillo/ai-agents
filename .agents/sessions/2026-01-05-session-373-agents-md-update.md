# Session 373 - 2026-01-05

## Session Info

- **Date**: 2026-01-05
- **Branch**: cursor/agent-documentation-update-2311
- **Starting Commit**: 7bc30af
- **Objective**: Update `AGENTS.md` to support `serena/*` tool naming and document Serena unavailability fallback.

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [ ] | Serena tools not available in this environment |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [ ] | Serena tools not available in this environment |
| MUST | Read `.agents/HANDOFF.md` | [x] | Read via file tool |
| MUST | Create this session log | [x] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [x] | Listed under Skill Inventory (via file glob; `pwsh` unavailable) |
| MUST | Read usage-mandatory memory | [x] | Read `.serena/memories/usage-mandatory.md` |
| MUST | Read PROJECT-CONSTRAINTS.md | [x] | Read `.agents/governance/PROJECT-CONSTRAINTS.md` |
| MUST | Read memory-index, load task-relevant memories | [x] | Read `memory-index` + `skills-documentation-index` + `documentation-003-fallback-preservation` |
| SHOULD | Import shared memories: `pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1` | [ ] | `pwsh` unavailable in this environment |
| MUST | Verify and declare current branch | [x] | `git branch --show-current` output recorded below |
| MUST | Confirm not on main/master | [x] | On feature branch |
| SHOULD | Verify git status | [x] | `git status --porcelain` returned empty |
| SHOULD | Note starting commit | [x] | `git log --oneline -1` recorded below |

### Skill Inventory

Available GitHub skills:

- `.claude/skills/github/scripts/reactions/Add-CommentReaction.ps1`
- `.claude/skills/github/scripts/pr/Add-PRReviewThreadReply.ps1`
- `.claude/skills/github/scripts/pr/Close-PR.ps1`
- `.claude/skills/github/scripts/pr/Detect-CopilotFollowUpPR.ps1`
- `.claude/skills/github/scripts/pr/Get-PRChecks.ps1`
- `.claude/skills/github/scripts/pr/Get-PRContext.ps1`
- `.claude/skills/github/scripts/pr/Get-PullRequests.ps1`
- `.claude/skills/github/scripts/pr/Get-PRReviewComments.ps1`
- `.claude/skills/github/scripts/pr/Get-PRReviewers.ps1`
- `.claude/skills/github/scripts/pr/Get-PRReviewThreads.ps1`
- `.claude/skills/github/scripts/pr/Get-ThreadById.ps1`
- `.claude/skills/github/scripts/pr/Get-ThreadConversationHistory.ps1`
- `.claude/skills/github/scripts/pr/Get-UnaddressedComments.ps1`
- `.claude/skills/github/scripts/pr/Get-UnresolvedReviewThreads.ps1`
- `.claude/skills/github/scripts/pr/Invoke-PRCommentProcessing.ps1`
- `.claude/skills/github/scripts/pr/Merge-PR.ps1`
- `.claude/skills/github/scripts/pr/New-PR.ps1`
- `.claude/skills/github/scripts/pr/Post-PRCommentReply.ps1`
- `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1`
- `.claude/skills/github/scripts/pr/Set-PRAutoMerge.ps1`
- `.claude/skills/github/scripts/pr/Test-PRMergeReady.ps1`
- `.claude/skills/github/scripts/pr/Test-PRMerged.ps1`
- `.claude/skills/github/scripts/pr/Unresolve-PRReviewThread.ps1`
- `.claude/skills/github/scripts/issue/Get-IssueContext.ps1`
- `.claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1`
- `.claude/skills/github/scripts/issue/New-Issue.ps1`
- `.claude/skills/github/scripts/issue/Post-IssueComment.ps1`
- `.claude/skills/github/scripts/issue/Set-IssueAssignee.ps1`
- `.claude/skills/github/scripts/issue/Set-IssueLabels.ps1`
- `.claude/skills/github/scripts/issue/Set-IssueMilestone.ps1`

### Git State

- **Status**: clean
- **Branch**: cursor/agent-documentation-update-2311
- **Starting Commit**: 7bc30af

### Branch Verification

**Current Branch**: cursor/agent-documentation-update-2311
**Matches Expected Context**: Yes

### Work Blocked Until

All MUST requirements above are marked complete.

---

## Work Log

### Update `AGENTS.md` Serena tool naming guidance

**Status**: Complete

**What was done**:
- Updated `AGENTS.md` to recognize both `mcp__serena__*` and `serena/*` tool naming and to document a fallback when Serena tools are unavailable.

**Files changed**:
- `AGENTS.md` - Clarified Serena initialization instructions and added `serena/*` equivalents in examples.

---

## Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| SHOULD | Export session memories: `pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "[query]" -SessionNumber NNN -Topic "topic"` | [ ] | Not run (`pwsh` unavailable) |
| MUST | Security review export (if exported): `grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [file].json` | [ ] | Not applicable (no export) |
| MUST | Complete session log (all sections filled) | [ ] | Pending |
| MUST | Update Serena memory (cross-session context) | [ ] | Serena tools not available in this environment |
| MUST | Run markdown lint | [ ] | Pending |
| MUST | Route to qa agent (feature implementation) | [ ] | Not applicable (documentation-only change) |
| MUST | Commit all changes (including .serena/memories) | [ ] | Pending |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [x] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [ ] | Not applicable |
| SHOULD | Invoke retrospective (significant sessions) | [ ] | Not applicable |
| SHOULD | Verify clean git status | [ ] | Pending |

### Lint Output

[Paste markdownlint output here]

### Final Git Status

[Paste git status output here]

### Commits This Session

- `[TBD]` - docs: clarify Serena tool naming in AGENTS.md

---

## Notes for Next Session

- Serena tools were not available in this environment; `AGENTS.md` now documents `serena/*` equivalents and an explicit unavailability fallback.
