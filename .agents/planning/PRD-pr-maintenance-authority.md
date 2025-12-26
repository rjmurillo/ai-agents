# PRD: PR Maintenance Workflow Enhancement - Bot Authority and Copilot Synthesis

**Date**: 2025-12-26
**Status**: Revised (Iteration 2)
**Owner**: Explainer Agent
**Target Release**: Next

## Introduction/Overview

The PR maintenance workflow incorrectly categorizes bot-authored PRs and fails to properly handle bot review scenarios. This PRD addresses 4 critical gaps that cause bot-authored PRs to be wrongly blocked, unaddressed comments to be ignored, and Copilot synthesis to fail. Fixing these gaps ensures bot-authored PRs receive appropriate automated handling while human-authored PRs continue to require manual intervention.

## Problem Statement

Four gaps prevent effective automated PR maintenance:

1. **Gap 1**: Bot-authored PRs with unresolvable conflicts are placed in Blocked instead of ActionRequired, preventing automated resolution attempts
2. **Gap 2**: Bot-authored PRs with unaddressed comments are not triggered for action unless reviewDecision equals CHANGES_REQUESTED
3. **Gap 3**: When rjmurillo-bot reviews copilot-swe-agent PRs, other bot feedback is not synthesized into @copilot prompts
4. **Gap 4**: PRs appear in both ActionRequired and Blocked lists, creating conflicting disposition

These gaps affect 6 PRs (#365, #353, #301, #255, #247, #235) and prevent automated workflow progression.

## Goals

1. Bot-authored PRs with unresolvable conflicts remain in ActionRequired (not moved to Blocked)
2. Bot-authored PRs with unaddressed comments trigger action regardless of reviewDecision state
3. Copilot-swe-agent PRs receive synthesized feedback from other bots via @copilot prompts
4. Each PR appears in exactly one status list (ActionRequired OR Blocked, never both)

## Non-Goals (Out of Scope)

1. Changing how human-authored PRs are handled (they should continue requiring manual intervention)
2. Modifying the conflict resolution algorithm itself (only changing disposition logic)
3. Supporting bots other than rjmurillo-bot, copilot-swe-agent, coderabbitai, cursor[bot], gemini-code-assist
4. Automatic merging of PRs without review
5. Backfilling previous PR dispositions (fix applies to future runs only)

## User Stories

### Story 1: Bot-Authored PR with Unresolvable Conflicts

**As** rjmurillo-bot (bot author)
**I want** my PR to remain in ActionRequired when automatic conflict resolution fails
**So that** I can manually resolve conflicts via `/pr-review` instead of requiring human intervention

**INVEST Validation**:
- **Independent**: Does not depend on other stories
- **Negotiable**: Could use different action mechanism than `/pr-review`
- **Valuable**: Enables automated conflict resolution for 5+ PRs
- **Estimable**: Clear scope (single conditional block)
- **Small**: Can be implemented in one session
- **Testable**: Can verify bot PRs in ActionRequired after failed resolution

**Acceptance Criteria**:
- **Given** a bot-authored PR (author = rjmurillo-bot)
- **When** automatic conflict resolution fails
- **Then** the PR is added to ActionRequired (not Blocked)
- **And** Reason equals 'MANUAL_CONFLICT_RESOLUTION'
- **And** Action equals '/pr-review to manually resolve conflicts'
- **And** Category equals 'agent-controlled'
- **And** human-authored PRs with conflicts are still added to Blocked (not ActionRequired)

### Story 2: Bot-Authored PR with Unaddressed Comments

**As** rjmurillo-bot (bot author)
**I want** my PR to trigger action when I have unaddressed bot comments
**So that** I can respond to feedback even when reviewDecision is not CHANGES_REQUESTED

**INVEST Validation**:
- **Independent**: Does not depend on Story 1
- **Negotiable**: Could define different threshold for unaddressed count
- **Valuable**: Addresses 5 PRs with 20+ unaddressed comments
- **Estimable**: Clear scope (extend condition check)
- **Small**: Can be implemented in one session
- **Testable**: Can verify PRs with comments trigger action

**Acceptance Criteria**:
- **Given** a bot-authored PR (author = rjmurillo-bot)
- **When** unaddressed bot comments exist (count > 0)
- **Then** the PR is added to ActionRequired
- **And** Reason equals 'UNADDRESSED_COMMENTS' (if reviewDecision is not CHANGES_REQUESTED)
- **And** Action equals '/pr-review via pr-comment-responder'
- **And** UnaddressedCount property is populated
- **And** human-authored PRs with unaddressed comments are NOT affected (existing behavior)

### Story 3a: Copilot PR Detection and Comment Collection

**As** rjmurillo-bot (bot reviewer on copilot-swe-agent PR)
**I want** to detect copilot-swe-agent PRs and collect feedback from other bots
**So that** I can identify PRs requiring synthesis

**INVEST Validation**:
- **Independent**: Does not depend on Stories 1-2
- **Negotiable**: Could use different bot detection pattern
- **Valuable**: Enables identification of synthesis-required PRs
- **Estimable**: Clear scope (detection + collection only)
- **Small**: Can be implemented in one session (no synthesis logic)
- **Testable**: Can verify correct PRs are identified

**Acceptance Criteria**:
- **Given** a PR authored by copilot-swe-agent (author matches 'copilot' pattern)
- **And** rjmurillo-bot is a reviewer
- **When** PR maintenance runs
- **Then** PR is identified as copilot-swe-agent PR
- **And** comments from other bots (not copilot) are collected
- **And** the PR is added to ActionRequired with Reason='COPILOT_SYNTHESIS_NEEDED'
- **And** CommentsToSynthesize count reflects non-copilot bot comments
- **And** if 0 comments from other bots exist, do NOT add to ActionRequired for synthesis

### Story 3b: Copilot Synthesis Prompt Generation

**As** rjmurillo-bot (bot reviewer on copilot-swe-agent PR)
**I want** to synthesize collected feedback into a @copilot prompt
**So that** copilot-swe-agent receives actionable consolidated feedback

**INVEST Validation**:
- **Independent**: Depends on Story 3a (comment collection)
- **Negotiable**: Could use different synthesis format
- **Valuable**: Enables automated feedback loop for copilot PRs
- **Estimable**: Clear scope (synthesis + posting only)
- **Small**: Can be implemented in one session (uses collected comments from 3a)
- **Testable**: Can verify @copilot prompt is posted

**Acceptance Criteria**:
- **Given** a copilot-swe-agent PR with CommentsToSynthesize > 0
- **When** synthesis is triggered
- **Then** a markdown prompt is generated following the synthesis format
- **And** the prompt is posted as a PR comment directed at @copilot
- **And** the prompt includes each bot's feedback with comment links
- **And** the prompt provides clear action items

### Story 4: Single List Disposition

**As** the PR maintenance system
**I want** each PR to appear in exactly one status list
**So that** there is no ambiguity about what action is required

**INVEST Validation**:
- **Independent**: Does not depend on Stories 1-3 (but complements them)
- **Negotiable**: Could prioritize ActionRequired or Blocked differently
- **Valuable**: Prevents confusion and duplicate work
- **Estimable**: Clear scope (deduplication logic)
- **Small**: Can be implemented in one session
- **Testable**: Can verify no duplicate entries

**Acceptance Criteria**:
- **Given** a PR is being processed
- **When** the PR qualifies for multiple status lists
- **Then** the PR appears in only one list based on priority (ActionRequired > Blocked)
- **And** if already in ActionRequired, conflict info is appended to existing entry
- **And** the entry includes HasConflicts flag if applicable
- **And** the Action field combines all required actions

## Functional Requirements

### FR1: Bot Authority Detection

The system must distinguish between bot-authored PRs and human-authored PRs.

**Implementation**:
- Check `$isAgentControlledBot` flag (author matches rjmurillo-bot)
- Use existing bot detection logic
- Apply authority rules only to bot-authored PRs

### FR2: Conflict Resolution Disposition

The system must route failed conflict resolutions based on author authority.

**Implementation** (lines 1359-1372 in Invoke-PRMaintenance.ps1):
- When conflict resolution fails for bot-authored PR: add to ActionRequired
- When conflict resolution fails for human-authored PR: add to Blocked
- Include MANUAL_CONFLICT_RESOLUTION reason for bot PRs

### FR3: Unaddressed Comments Trigger

The system must trigger action for unaddressed bot comments regardless of reviewDecision.

**Comment State Detection**:
- **Unaddressed** = comment from bot that has NO replies from PR author (rjmurillo-bot)
- Eyes reaction does NOT count as "addressed" (acknowledgment only)
- Use existing `Get-UnacknowledgedComments` function which returns comments where `reactions.eyes == 0`
- A comment is considered addressed when it has a reply containing resolution info

**Implementation** (lines 1270-1288 in Invoke-PRMaintenance.ps1):
- Check unaddressed comment count BEFORE reviewDecision check
- Trigger action if `$unacked.Count -gt 0` OR `$hasChangesRequested`
- Include UnaddressedCount in ActionRequired entry
- Use reason 'UNADDRESSED_COMMENTS' when reviewDecision is not CHANGES_REQUESTED

### FR4: Copilot Synthesis Workflow

The system must synthesize bot feedback for copilot-swe-agent PRs.

**Detection Logic** (new in Invoke-PRMaintenance.ps1):
```powershell
$isCopilotPR = ($botInfo.Category -eq 'mention-triggered') -and ($authorLogin -match 'copilot')
```

**Implementation** (new function `Invoke-CopilotSynthesis`):
- Detect copilot-swe-agent authorship using pattern match
- Collect comments from other bots (coderabbitai, cursor[bot], gemini-code-assist) excluding copilot
- Generate synthesis prompt: "@copilot Please address the following feedback: [summary]"
- Post as PR comment via `gh pr comment`
- Add to ActionRequired with COPILOT_SYNTHESIS_NEEDED reason

**Edge Cases**:
- If only 1 bot has comments: still generate synthesis
- If 0 other bots have comments: do NOT post synthesis (no COPILOT_SYNTHESIS_NEEDED reason)
- If rjmurillo-bot is not a reviewer: do not trigger synthesis

**Protocol Document Updates** (.agents/architecture/bot-author-feedback-protocol.md):
- Add to rjmurillo-bot Activation Triggers table (line 133):
  ```markdown
  | **Reviewer on Copilot PR** | rjmurillo-bot reviews copilot-swe-agent PR | N/A | Synthesize bot feedback for @copilot |
  ```
- Add new section "Copilot Synthesis Workflow" after line 200:
  - Define when synthesis triggers
  - Document synthesis format
  - Define bot authority boundary: "Bot reviewer CANNOT directly modify mention-triggered PRs - must delegate via @copilot"

### FR5: Single List Guarantee

The system must ensure each PR appears in exactly one status list.

**Implementation** (lines 1359-1372 in Invoke-PRMaintenance.ps1):
```powershell
$alreadyInActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $pr.number }
if ($alreadyInActionRequired) {
    # Update existing entry with conflict info
    $alreadyInActionRequired.HasConflicts = $true
    $alreadyInActionRequired.Action = "$($alreadyInActionRequired.Action) + resolve conflicts"
}
elseif ($isAgentControlledBot) {
    # Add to ActionRequired (not Blocked)
    $null = $results.ActionRequired.Add(@{...})
}
else {
    # Add to Blocked (non-bot PR)
    $null = $results.Blocked.Add(@{...})
}
```

**Priority Order**:
1. ActionRequired (bot can act) - takes precedence
2. Blocked (human intervention required) - fallback only

**Merge Behavior**:
- When PR already in ActionRequired: append conflict info to existing entry
- Do NOT create duplicate entry in Blocked

## Technical Considerations

### Files to Modify

1. **scripts/Invoke-PRMaintenance.ps1**
   - Lines 1270-1288: Unaddressed comments logic
   - Lines 1359-1372: Conflict resolution disposition
   - New function: `Invoke-CopilotSynthesis`

2. **.agents/architecture/bot-author-feedback-protocol.md**
   - Add scenario: "Bot as reviewer on mention-triggered PR"
   - Add action type: "Copilot Synthesis"
   - Define bot authority boundaries

3. **.agents/memories/pr-changes-requested-semantics.md**
   - Document that unaddressed comments trigger action regardless of reviewDecision
   - Document copilot synthesis workflow

### Data Structures

**ActionRequired entry**:

```powershell
@{
    PR = [int]
    Author = [string]
    Reason = [string] # MANUAL_CONFLICT_RESOLUTION | UNADDRESSED_COMMENTS | CHANGES_REQUESTED | COPILOT_SYNTHESIS_NEEDED
    Title = [string]
    Category = [string] # agent-controlled | synthesis-required
    Action = [string]
    UnaddressedCount = [int] # optional
    CommentsToSynthesize = [int] # optional
    HasConflicts = [bool] # optional
}
```

### Test Coverage Required

**Unit Tests (Pester)**:
1. **Pester Test**: Bot-authored PR with unresolvable conflicts -> ActionRequired (not Blocked)
2. **Pester Test**: Bot-authored PR with unaddressed comments (reviewDecision = null) -> ActionRequired
3. **Pester Test**: Bot reviewer on copilot-swe-agent PR -> COPILOT_SYNTHESIS_NEEDED
4. **Pester Test**: PR with conflicts and CHANGES_REQUESTED -> appears in ActionRequired only (not both lists)
5. **Pester Test**: Human-authored PR with unresolvable conflicts -> Blocked (existing behavior preserved)
6. **Pester Test**: Copilot PR with 0 other bot comments -> no COPILOT_SYNTHESIS_NEEDED (edge case)

**Integration Test**:
7. **Integration Test**: Run Invoke-PRMaintenance against 6 affected PRs (#365, #353, #301, #255, #247, #235) and verify:
   - Bot-authored PRs with conflicts appear in ActionRequired (not Blocked)
   - Unaddressed comments trigger action regardless of reviewDecision
   - Copilot synthesis generates @copilot prompt for PR #247
   - No PR appears in both lists

### Dependencies

**None blocking**. All changes are internal to PR maintenance workflow.

**Related Documentation**:
- .agents/architecture/bot-author-feedback-protocol.md
- .agents/memories/pr-changes-requested-semantics.md
- .agents/qa/PR-402/2025-12-26-gap-diagnostics.md

## Design Considerations

### Copilot Synthesis Format

The @copilot prompt should:
- Include PR context (title, number)
- List each bot's feedback with comment links
- Provide clear action items
- Use markdown formatting for readability

**Example**:

```markdown
@copilot Please address the following feedback on PR #247:

**coderabbitai** (3 comments):
- [Security concern about input validation](link)
- [Performance issue with async handling](link)
- [Missing null check in handler](link)

**cursor[bot]** (2 comments):
- [Type safety issue in response model](link)
- [Missing error handling](link)

Please implement fixes for these issues and update the PR.
```

### Priority Order

When a PR qualifies for multiple lists, priority order is:
1. ActionRequired (bot can act)
2. Blocked (human intervention required)

## Success Metrics

1. **Zero bot-authored PRs in Blocked due to conflicts**: All bot PRs with conflicts appear in ActionRequired
2. **100% of unaddressed comments trigger action**: No bot-authored PRs with comments are ignored
3. **Copilot synthesis produces @copilot prompt**: All copilot-swe-agent PRs receive synthesized feedback
4. **Zero duplicate PR entries**: Each PR appears in exactly one list

**Measurement**:
- Run PR maintenance workflow on current PR set (6 affected PRs)
- Validate disposition matches expected behavior
- Verify no regressions in human-authored PR handling

## Open Questions

None. All requirements are defined based on gap diagnostics.

## Related Documents

- **Gap Diagnostics**: .agents/qa/PR-402/2025-12-26-gap-diagnostics.md
- **Protocol**: .agents/architecture/bot-author-feedback-protocol.md
- **Memory**: .agents/memories/pr-changes-requested-semantics.md
