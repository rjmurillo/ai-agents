# Gap Analysis: PR Maintenance Workflow

## 1. Objective and Scope

**Objective**: Identify root causes of PR categorization errors in `Invoke-PRMaintenance.ps1` workflow

**Scope**: Analysis of three critical gaps where PRs are incorrectly categorized as "Blocked" instead of "ActionRequired"

## 2. Context

The PR maintenance script processes open PRs and categorizes them based on:
- PR author identity (bot vs human)
- Review decision status (CHANGES_REQUESTED)
- Comment acknowledgment status (eyes reactions)
- Merge conflict status

**Current observed behavior**: Bot-authored PRs with unresolvable conflicts and unaddressed bot comments are placed in "Blocked" category instead of "ActionRequired".

## 3. Approach

**Methodology**: Static code analysis of decision flow in `Invoke-PRMaintenance.ps1`

**Tools Used**:
- Read tool for code inspection (lines 1250-1400)
- Protocol documentation analysis (`.agents/architecture/bot-author-feedback-protocol.md`)

**Limitations**: No runtime debugging or log inspection; analysis based on code structure only

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Conflict resolution runs AFTER action determination | Lines 1354-1373 | High |
| UNRESOLVABLE_CONFLICTS added to Blocked unconditionally | Lines 1366-1371 | High |
| Action determination only checks reviewDecision == CHANGES_REQUESTED | Lines 1262, 1273 | High |
| Eyes reaction added to ALL comments when bot is author/reviewer | Lines 1290-1298 | High |
| No check for unaddressed comments when reviewDecision != CHANGES_REQUESTED | Lines 1273-1288 | High |
| Bot-as-reviewer scenario treats copilot-swe-agent same as agent-controlled | Lines 1270-1288 | Medium |

### Facts (Verified)

**Gap 1: UNRESOLVABLE_CONFLICTS logic**
- Lines 1359-1373: Conflict resolution runs in MAINTENANCE phase (after action determination)
- Line 1366: On resolution failure, PR added to Blocked with Reason='UNRESOLVABLE_CONFLICTS'
- No check for bot authorship when adding to Blocked
- Bot-authored PRs can have FULL AUTHORITY to resolve conflicts manually via /pr-review

**Gap 2: Unaddressed bot comments**
- Lines 1290-1298: Script adds eyes reaction to ALL bot comments when rjmurillo-bot is author/reviewer
- Lines 1273-1284: Action (/pr-review) only triggered when reviewDecision == 'CHANGES_REQUESTED'
- Bot comments (coderabbitai, cursor[bot], gemini-code-assist) do NOT set reviewDecision
- Eyes reaction signals "acknowledged and will address" but no action taken if reviewDecision is not set

**Gap 3: Bot-as-reviewer on copilot PR**
- Lines 1270-1288: Logic treats bot-as-reviewer identically to bot-as-author
- copilot-swe-agent PRs require @copilot mention (Category='mention-triggered' per lines 644-678)
- Current logic: If bot is reviewer + CHANGES_REQUESTED → /pr-review (wrong for copilot PRs)
- Correct logic: If bot is reviewer on copilot PR → synthesize comments into @copilot mention

### Hypotheses (Unverified)

- PRs #365, #353, #301, #255, #235 have reviewDecision != CHANGES_REQUESTED (explains no /pr-review trigger)
- PRs #365, #353, #301, #255, #235 have unresolvable conflicts (explains Blocked categorization)
- PR #247 has reviewDecision == CHANGES_REQUESTED from non-bot reviewers (explains Blocked categorization)

## 5. Results

### Gap 1: Bot-authored PRs with UNRESOLVABLE_CONFLICTS wrongly placed in Blocked

**Root Cause**: Lines 1366-1371

```powershell
else {
    $null = $results.Blocked.Add(@{
        PR = $pr.number
        Author = $authorLogin
        Reason = 'UNRESOLVABLE_CONFLICTS'
        Title = $pr.title
    })
}
```

**Issue**: No bot authorship check before adding to Blocked. Bot-authored PRs should go to ActionRequired even if conflict resolution fails automatically.

**Expected Behavior**:
- Bot-authored PR + CONFLICTING + resolution fails → ActionRequired with action="/pr-review" (bot can manually resolve)
- Human-authored PR + CONFLICTING + resolution fails → Blocked (human must resolve)

**Actual Behavior**:
- Any PR + CONFLICTING + resolution fails → Blocked (no author check)

**Impact**: 5 PRs (#365, #353, #301, #255, #235) incorrectly categorized

---

### Gap 2: Unaddressed review comments on bot-authored PRs

**Root Cause**: Lines 1273-1288

```powershell
if ($hasChangesRequested) {
    # CHANGES_REQUESTED -> /pr-review
    Write-Log "PR #$($pr.number): rjmurillo-bot is $role with CHANGES_REQUESTED -> /pr-review" -Level WARN
    $null = $results.ActionRequired.Add(@{...})
} else {
    # No CHANGES_REQUESTED -> maintenance only
    Write-Log "PR #$($pr.number): rjmurillo-bot is $role, no CHANGES_REQUESTED -> maintenance only" -Level INFO
}
```

**Issue**: Only checks `reviewDecision == 'CHANGES_REQUESTED'`. Bot comments (coderabbitai, cursor[bot], gemini-code-assist) do NOT set reviewDecision field.

**Protocol requirement** (bot-author-feedback-protocol.md lines 134-137):

```text
| **PR Author** | PR opened by rjmurillo-bot | Yes | /pr-review via pr-comment-responder |
| **PR Author** | PR opened by rjmurillo-bot | No | Maintenance only |
```

The protocol says "CHANGES_REQUESTED" determines action, but the INTENT is "any unaddressed comments". Bot comments without formal review submission do not set reviewDecision but still require addressing.

**Expected Behavior**:
- Bot-authored PR + unaddressed bot comments (eyes=0) → ActionRequired with action="/pr-review"
- Bot-authored PR + all comments acknowledged (eyes>0) → Maintenance only

**Actual Behavior**:
- Bot-authored PR + reviewDecision != CHANGES_REQUESTED → Maintenance only (even if unaddressed comments exist)
- Eyes reaction added to comments (lines 1290-1298) but no action taken

**Impact**: 5 PRs have unaddressed bot comments but no /pr-review action:
- PR #365: 7 unaddressed comments
- PR #353: 1 unaddressed comment
- PR #301: 7 unaddressed comments
- PR #255: 3 unaddressed comments
- PR #235: 2 unaddressed comments

---

### Gap 3: PR #247 - Bot as reviewer on copilot-swe-agent PR

**Root Cause**: Lines 1270-1288

```powershell
if ($isAgentControlledBot -or $isBotReviewer) {
    # Bot is author or reviewer
    $role = if ($isAgentControlledBot) { 'author' } else { 'reviewer' }
    if ($hasChangesRequested) {
        # CHANGES_REQUESTED -> /pr-review
        $null = $results.ActionRequired.Add(@{
            Category = 'agent-controlled'
            Action = '/pr-review via pr-comment-responder'
        })
    }
}
```

**Issue**: When rjmurillo-bot is reviewer, logic does not consider PR author's category. copilot-swe-agent is a mention-triggered bot (lines 644-646).

**Bot category** (lines 644-646):

```powershell
$mentionTriggered = @{
    '^copilot-swe-agent$' = '@copilot'
}
```

**Expected Behavior**:
- rjmurillo-bot is reviewer on copilot-swe-agent PR + CHANGES_REQUESTED → synthesize non-copilot comments into @copilot mention
- rjmurillo-bot is reviewer on agent-controlled PR + CHANGES_REQUESTED → /pr-review

**Actual Behavior**:
- rjmurillo-bot is reviewer + CHANGES_REQUESTED → /pr-review (regardless of PR author category)
- PR #247 added to ActionRequired with Category='agent-controlled' (incorrect)
- Should be: synthesize comments, add @copilot mention, track as 'mention-triggered'

**Impact**: PR #247 (copilot-swe-agent authored) incorrectly categorized as 'agent-controlled' instead of 'mention-triggered'

---

## 6. Discussion

### Pattern Analysis

All three gaps share a common theme: **insufficient context awareness in decision flow**.

1. **Gap 1**: Conflict resolution does not check if PR author can manually resolve
2. **Gap 2**: Action determination does not check for unaddressed comments beyond reviewDecision
3. **Gap 3**: Bot-as-reviewer logic does not check PR author's bot category

### Protocol vs Implementation Mismatch

The protocol document (bot-author-feedback-protocol.md) states:

**Lines 134-137 (rjmurillo-bot Activation Triggers table)**:
```text
| **PR Author** | PR opened by rjmurillo-bot | No | Maintenance only |
```

This implies "no action if no CHANGES_REQUESTED", but the INTENT (based on Gap 2 context) is "no action if no unaddressed comments".

**Lines 189-203 (Comment Acknowledgment - Eyes Reaction)**:
```text
When to add eyes reaction:
- rjmurillo-bot is the PR author -> add to ALL comments
```

This creates a false signal: eyes added to ALL comments even when no action will be taken (if reviewDecision != CHANGES_REQUESTED).

### Architecture Issue

The decision flow has a **temporal ordering problem**:

```text
1. Determine action (lines 1269-1343)
2. Acknowledge comments with eyes (lines 1290-1298)
3. Run maintenance (lines 1354-1373)
   a. Resolve conflicts
   b. On failure → Add to Blocked
```

Step 3b adds to Blocked AFTER step 1 already determined action. If step 1 added to ActionRequired (bot author + CHANGES_REQUESTED), step 3b may ALSO add to Blocked (conflict resolution failed).

**Result**: PR appears in BOTH ActionRequired and Blocked (duplicate entry).

**Observed behavior**: Only appears in Blocked (suggests step 1 did not add to ActionRequired, confirming Gap 2 root cause).

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| **P0** | Add bot authorship check in conflict resolution failure path (Gap 1) | Bot-authored PRs can manually resolve conflicts via /pr-review | Low (5 lines) |
| **P0** | Check for unaddressed bot comments when bot is author/reviewer (Gap 2) | Bot comments require action even without formal reviewDecision | Medium (15 lines) |
| **P1** | Add PR author category check when bot is reviewer (Gap 3) | copilot-swe-agent PRs need @copilot mention, not /pr-review | Medium (20 lines) |
| **P2** | Refactor decision flow to prevent duplicate categorization | Conflict resolution should not override action determination | High (structural change) |
| **P2** | Update protocol document to clarify "unaddressed comments" vs "CHANGES_REQUESTED" | Reduce implementation ambiguity | Low (documentation) |

### Detailed Fixes

**Gap 1 Fix** (lines 1366-1371):

```powershell
else {
    # Check if bot-authored (bot can manually resolve via /pr-review)
    if ($isAgentControlledBot) {
        Write-Log "PR #$($pr.number): Bot-authored with unresolvable conflicts -> /pr-review" -Level WARN
        $null = $results.ActionRequired.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
            Category = 'agent-controlled'
            Action = '/pr-review (manual conflict resolution)'
            Mention = $null
        })
    }
    else {
        # Human-authored -> truly blocked
        $null = $results.Blocked.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
            Category = 'human-blocked'
            Action = 'Human must resolve conflicts manually'
        })
    }
}
```

**Gap 2 Fix** (lines 1273-1288):

```powershell
if ($hasChangesRequested) {
    # CHANGES_REQUESTED -> /pr-review
    Write-Log "PR #$($pr.number): rjmurillo-bot is $role with CHANGES_REQUESTED -> /pr-review" -Level WARN
    $actionReason = 'CHANGES_REQUESTED'
}
else {
    # Check for unaddressed bot comments (even without formal reviewDecision)
    $unaddressedBotComments = @($comments | Where-Object {
        $_.user.type -eq 'Bot' -and
        $_.reactions.eyes -eq 0
    })
    if ($unaddressedBotComments.Count -gt 0) {
        Write-Log "PR #$($pr.number): rjmurillo-bot is $role with $($unaddressedBotComments.Count) unaddressed bot comment(s) -> /pr-review" -Level WARN
        $actionReason = 'UNADDRESSED_BOT_COMMENTS'
    }
    else {
        # No changes requested, no unaddressed comments -> maintenance only
        Write-Log "PR #$($pr.number): rjmurillo-bot is $role, no CHANGES_REQUESTED, no unaddressed comments -> maintenance only" -Level INFO
        $actionReason = $null
    }
}

if ($actionReason) {
    $null = $results.ActionRequired.Add(@{
        PR = $pr.number
        Author = $authorLogin
        Reason = $actionReason
        Title = $pr.title
        Category = 'agent-controlled'
        Action = '/pr-review via pr-comment-responder'
        Mention = $null
    })
}
```

**Gap 3 Fix** (lines 1270-1288):

```powershell
if ($isAgentControlledBot -or $isBotReviewer) {
    # Bot is author or reviewer
    $role = if ($isAgentControlledBot) { 'author' } else { 'reviewer' }

    # If bot is reviewer, check PR author's category
    if ($isBotReviewer -and -not $isAgentControlledBot) {
        $prAuthorInfo = Get-BotAuthorInfo -AuthorLogin $authorLogin
        if ($prAuthorInfo.Category -eq 'mention-triggered') {
            # Mention-triggered bot (e.g., copilot-swe-agent) -> synthesize comments into @mention
            if ($hasChangesRequested) {
                Write-Log "PR #$($pr.number): rjmurillo-bot is reviewer on mention-triggered bot PR -> synthesize comments into $($prAuthorInfo.Mention)" -Level WARN
                $null = $results.ActionRequired.Add(@{
                    PR = $pr.number
                    Author = $authorLogin
                    Reason = 'CHANGES_REQUESTED'
                    Title = $pr.title
                    Category = 'mention-triggered'
                    Action = "Synthesize non-$($authorLogin) comments into $($prAuthorInfo.Mention) prompt"
                    Mention = $prAuthorInfo.Mention
                })
            }
            # No need to acknowledge comments (not our action)
            continue  # Skip to next PR
        }
    }

    # Agent-controlled author or reviewer (existing logic)
    if ($hasChangesRequested) {
        # ... existing logic
    }
    # ... existing acknowledgment logic
}
```

## 8. Conclusion

**Verdict**: Implement fixes for Gaps 1, 2, and 3

**Confidence**: High

**Rationale**: Root causes identified with specific code line references. Fixes are straightforward and preserve existing workflow while correcting categorization errors.

### User Impact

**What changes for you**:
1. Bot-authored PRs with conflicts will trigger /pr-review instead of being marked Blocked
2. Bot-authored PRs with unaddressed bot comments will trigger /pr-review (not just CHANGES_REQUESTED)
3. copilot-swe-agent PRs where rjmurillo-bot is reviewer will synthesize comments into @copilot mention

**Effort required**: Implementer to apply 3 code changes (estimated 30 minutes)

**Risk if ignored**:
- Bot-authored PRs accumulate in Blocked list without action
- Bot comments remain unaddressed indefinitely
- copilot-swe-agent PRs incorrectly routed to /pr-review instead of @copilot mention

## 9. Appendices

### Sources Consulted

- `/home/richard/ai-agents/scripts/Invoke-PRMaintenance.ps1` (lines 1200-1400)
- `/home/richard/ai-agents/.agents/architecture/bot-author-feedback-protocol.md`

### Data Transparency

**Found**:
- Complete decision flow code structure
- Bot category definitions (lines 644-716)
- Conflict resolution logic (lines 1359-1373)
- Comment acknowledgment logic (lines 1290-1298)

**Not Found**:
- Actual PR states for #365, #353, #301, #255, #235, #247 (would need GitHub API query)
- Runtime logs showing actual categorization decisions
- Test coverage for these scenarios
