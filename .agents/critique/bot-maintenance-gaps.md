# Plan Critique: Bot Author Feedback Protocol Implementation

## Verdict

**NEEDS REVISION**

## Summary

The bot-author-feedback-protocol.md specification and Invoke-PRMaintenance.ps1 implementation contain CRITICAL gaps across three dimensions:

1. **Conflict resolution authority** - bot-authored PRs blocked by resolvable conflicts
2. **Comment acknowledgment trigger** - unaddressed comments not triggering action
3. **Synthesizer role specification** - protocol silent on reviewer synthesis responsibility

All three gaps stem from incomplete specification rather than implementation failure.

## Issues Found

### Critical (Must Fix)

#### Issue Set 1: Bot-authored PRs with conflicts wrongly blocked

**Verdict**: SPEC_GAP

**Evidence**:

Protocol specification (bot-author-feedback-protocol.md, lines 133-140):

```text
| Trigger | Condition | CHANGES_REQUESTED? | Action |
|---------|-----------|-------------------|--------|
| **PR Author** | PR opened by rjmurillo-bot | Yes | /pr-review via pr-comment-responder |
| **PR Author** | PR opened by rjmurillo-bot | No | Maintenance only |
```

Implementation (Invoke-PRMaintenance.ps1, lines 1359-1372):

```powershell
if ($pr.mergeable -eq 'CONFLICTING') {
    Write-Log "PR #$($pr.number) has merge conflicts - attempting resolution" -Level ACTION
    $resolved = Resolve-PRConflicts -Owner $Owner -Repo $Repo -PRNumber $pr.number -BranchName $pr.headRefName -TargetBranch $pr.baseRefName
    if ($resolved) {
        $results.ConflictsResolved++
    }
    else {
        $null = $results.Blocked.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
        })
    }
}
```

**Gap Analysis**:

- **Protocol says**: "Maintenance only" when bot-authored PR has NO CHANGES_REQUESTED
- **Reality**: PRs #365, #353, #301, #255, #235 ALL authored by rjmurillo-bot with conflicts
- **Implementation does**: Attempts auto-resolution, blocks if fails
- **Missing specification**: "Can bot author resolve ANY conflicts on its own PRs, or only auto-resolvable ones?"

**Severity**: P0

**Blocking**: YES

**Rationale**:

Bot has full authority to modify its own PRs. Conflicts are mechanical git state, NOT logical review state. Implementation correctly attempts resolution but wrongly blocks bot-authored PRs when auto-resolution fails. Protocol should clarify:

1. Bot author CAN resolve ALL conflicts on own PRs (not just .agents/HANDOFF.md and sessions)
2. Blocked list should ONLY contain human-intervention scenarios

**Acceptance Criteria Missing**:

```text
GIVEN: rjmurillo-bot-authored PR with UNRESOLVABLE_CONFLICTS
WHEN: Protocol executes
THEN:
  - Attempt manual conflict resolution (checkout, merge, resolve, commit, push)
  - Add to ActionRequired with Reason='CONFLICTS_NEED_REVIEW' (NOT Blocked)
  - Invoke /pr-review to assess if conflicts indicate deeper issues
```

---

#### Issue Set 2: Unaddressed comments not triggering action

**Verdict**: SPEC_GAP

**Evidence**:

Protocol specification (bot-author-feedback-protocol.md, lines 189-202):

```text
**When to add eyes reaction:**

- rjmurillo-bot is the PR author -> add to ALL comments
- rjmurillo-bot is assigned as reviewer -> add to ALL comments
- @rjmurillo-bot is explicitly mentioned -> add ONLY to that comment
```

Implementation (Invoke-PRMaintenance.ps1, lines 1270-1298):

```powershell
if ($isAgentControlledBot -or $isBotReviewer) {
    # Bot is author or reviewer
    $role = if ($isAgentControlledBot) { 'author' } else { 'reviewer' }
    if ($hasChangesRequested) {
        # CHANGES_REQUESTED -> /pr-review
        Write-Log "PR #$($pr.number): rjmurillo-bot is $role with CHANGES_REQUESTED -> /pr-review" -Level WARN
        $null = $results.ActionRequired.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'CHANGES_REQUESTED'
            ...
        })
    } else {
        # No CHANGES_REQUESTED -> maintenance only
        Write-Log "PR #$($pr.number): rjmurillo-bot is $role, no CHANGES_REQUESTED -> maintenance only" -Level INFO
    }

    # Acknowledge ALL comments when author or reviewer (reuse pre-fetched comments)
    $unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
    foreach ($comment in $unacked) {
        Write-Log "Acknowledging comment $($comment.id) from $($comment.user.login)" -Level ACTION
        $acked = Add-CommentReaction -Owner $Owner -Repo $Repo -CommentId $comment.id
        if ($acked) {
            $results.CommentsAcknowledged++
        }
    }
}
```

**Gap Analysis**:

- **Protocol says**: Acknowledge ALL comments when bot is author/reviewer
- **Implementation does**: Acknowledges ALL comments correctly
- **BUT**: Only invokes /pr-review when `reviewDecision == 'CHANGES_REQUESTED'`
- **Reality**: PRs #365, #353, #301, #255, #235 have 20+ unaddressed bot comments BUT reviewDecision != CHANGES_REQUESTED
- **Missing specification**: "Should unaddressed comments trigger /pr-review even without CHANGES_REQUESTED?"

**Severity**: P0

**Blocking**: YES

**Rationale**:

GitHub's `reviewDecision` field reflects formal review state (APPROVED, CHANGES_REQUESTED, REVIEW_REQUIRED). Bot comments may exist WITHOUT formal review submission. Protocol assumes comments == CHANGES_REQUESTED but this is NOT guaranteed.

**Evidence from PRs**:

- PR #365: 22 unaddressed bot comments, reviewDecision = null
- PR #353: 18 unaddressed bot comments, reviewDecision = null
- PR #301: 25 unaddressed bot comments, reviewDecision = null

**Acceptance Criteria Missing**:

```text
GIVEN: rjmurillo-bot-authored PR with unaddressed bot comments AND reviewDecision != CHANGES_REQUESTED
WHEN: Protocol executes
THEN:
  - Count unaddressed comments (reactions.eyes == 0 AND user.type == 'Bot')
  - If count > threshold (e.g., 5), add to ActionRequired with Reason='UNADDRESSED_COMMENTS'
  - Invoke /pr-review to process comments
```

**Alternative Specification** (if comments should be ignored without formal review):

```text
GIVEN: Bot-authored PR with 20+ unaddressed comments BUT reviewDecision != CHANGES_REQUESTED
WHEN: Protocol executes
THEN:
  - Acknowledge comments with eyes reaction
  - Do NOT invoke /pr-review (wait for formal CHANGES_REQUESTED)
  - Rationale: Comments may be informational, not blocking
```

Protocol MUST choose one approach and document it.

---

#### Issue Set 3: Bot as reviewer should synthesize for other bots

**Verdict**: SPEC_GAP

**Evidence**:

Protocol specification: **NO MENTION** of synthesizer role

Implementation: **NO LOGIC** for synthesizer role

**Gap Analysis**:

User context describes:

> PR #247 by copilot-swe-agent:
> - rjmurillo-bot is REVIEWER
> - CHANGES_REQUESTED status
> - Other bots (coderabbitai, cursor[bot]) left feedback not directed @copilot
> - rjmurillo-bot should synthesize and direct to @copilot

**Missing specification**:

1. When is rjmurillo-bot a "synthesizer" vs. "reviewer"?
2. What triggers synthesis behavior?
3. What format should synthesis take?
4. Which bots' feedback should be synthesized?

**Severity**: P1

**Blocking**: NO (edge case, not core workflow)

**Rationale**:

Synthesizer role is valid but undefined. Scenario:

- Human-authored PR (or mention-triggered bot PR like copilot-swe-agent)
- rjmurillo-bot added as reviewer
- Other bots (cursor[bot], coderabbitai) leave feedback
- Original PR author bot (copilot) requires @copilot mention to act
- rjmurillo-bot should aggregate feedback and direct to @copilot

**Acceptance Criteria Missing**:

```text
GIVEN: PR authored by mention-triggered bot (e.g., copilot-swe-agent)
  AND: rjmurillo-bot is requested reviewer
  AND: Other bots have left unaddressed comments
  AND: reviewDecision == CHANGES_REQUESTED
WHEN: Protocol executes
THEN:
  - Detect PR author is mention-triggered (Category == 'mention-triggered')
  - Aggregate all unaddressed bot comments
  - Post synthesis comment:
    "@copilot - addressing feedback from multiple reviewers:

    **cursor[bot]**:
    - [Summary of cursor feedback]

    **coderabbitai**:
    - [Summary of coderabbitai feedback]

    Please address these items."
  - Add eyes to all synthesized comments
  - Add to ActionRequired with Reason='SYNTHESIS_COMPLETE'
```

**Detection Logic** (pseudocode):

```powershell
$authorInfo = Get-BotAuthorInfo -AuthorLogin $pr.author.login
$isBotReviewer = Test-IsBotReviewer -ReviewRequests $pr.reviewRequests
$hasChangesRequested = $pr.reviewDecision -eq 'CHANGES_REQUESTED'

if ($authorInfo.Category -eq 'mention-triggered' -and $isBotReviewer -and $hasChangesRequested) {
    # Synthesizer mode
    $otherBotComments = Get-UnaddressedBotComments -Excluding @('rjmurillo-bot', $pr.author.login)
    if ($otherBotComments.Count -gt 0) {
        Post-SynthesisComment -PRNumber $pr.number -Comments $otherBotComments -MentionPattern $authorInfo.Mention
    }
}
```

---

### Important (Should Fix)

None identified - all gaps are Critical.

---

### Minor (Consider)

None identified - all gaps are Critical.

---

## Questions for Planner

1. **Conflict resolution authority**: Should bot-authored PRs be allowed to resolve ALL conflicts (not just auto-resolvable), or should non-trivial conflicts trigger human escalation?

2. **Comment threshold**: What threshold of unaddressed comments should trigger /pr-review even without CHANGES_REQUESTED? (Current: 0 = ignored, Proposed: 5+)

3. **Synthesizer activation**: Should synthesizer role be automatic when bot is reviewer on mention-triggered bot PRs, or require explicit configuration/flag?

4. **Synthesis format**: Should synthesis be:
   - Single aggregated comment with all bot feedback?
   - Separate reply to each bot comment with @mention to PR author?
   - Both (aggregate + individual replies)?

## Recommendations

### Specification Updates Required

1. **Add Conflict Resolution Authority section** to bot-author-feedback-protocol.md:

   ```markdown
   ## Conflict Resolution Authority

   ### Bot-Authored PRs

   When rjmurillo-bot is the PR author, it has FULL authority to resolve conflicts:

   - Auto-resolvable conflicts (.agents/HANDOFF.md, sessions/*): Use --theirs strategy
   - Non-auto-resolvable conflicts: Manual resolution allowed
   - If conflicts indicate logical issues (not just mechanical git state): Add to ActionRequired with Reason='CONFLICTS_NEED_REVIEW'

   ### Human-Authored PRs

   When rjmurillo-bot is NOT the author:

   - Auto-resolvable conflicts: Resolve with --theirs
   - Non-auto-resolvable conflicts: Block with UNRESOLVABLE_CONFLICTS
   ```

2. **Add Comment Threshold Trigger** to Activation Triggers table:

   ```markdown
   | Trigger | Condition | CHANGES_REQUESTED? | Action |
   |---------|-----------|-------------------|--------|
   | **Unaddressed Comments** | Bot author/reviewer + 5+ unaddressed bot comments | No | /pr-review via pr-comment-responder |
   ```

3. **Add Synthesizer Role section**:

   ```markdown
   ## Synthesizer Role

   When rjmurillo-bot is a REVIEWER on a mention-triggered bot's PR:

   ### Activation

   - PR authored by mention-triggered bot (copilot-swe-agent, copilot[bot])
   - rjmurillo-bot is requested reviewer
   - CHANGES_REQUESTED status
   - Other bots have left unaddressed comments

   ### Behavior

   - Aggregate feedback from all non-author bots
   - Post single synthesis comment with @mention to PR author
   - Acknowledge all synthesized comments with eyes
   - Add to ActionRequired with Reason='SYNTHESIS_COMPLETE'
   ```

### Implementation Updates Required

1. **Modify conflict blocking logic** (Invoke-PRMaintenance.ps1, lines 1359-1372):

   ```powershell
   if ($pr.mergeable -eq 'CONFLICTING') {
       Write-Log "PR #$($pr.number) has merge conflicts - attempting resolution" -Level ACTION
       $resolved = Resolve-PRConflicts -Owner $Owner -Repo $Repo -PRNumber $pr.number -BranchName $pr.headRefName -TargetBranch $pr.baseRefName

       if (-not $resolved) {
           # Check if bot is the author - if so, add to ActionRequired (not Blocked)
           if ($isAgentControlledBot) {
               $null = $results.ActionRequired.Add(@{
                   PR = $pr.number
                   Author = $authorLogin
                   Reason = 'CONFLICTS_NEED_REVIEW'
                   Title = $pr.title
                   Category = 'agent-controlled'
                   Action = '/pr-review to assess conflict resolution'
               })
           } else {
               # Human-authored or non-agent bot - truly blocked
               $null = $results.Blocked.Add(@{
                   PR = $pr.number
                   Author = $authorLogin
                   Reason = 'UNRESOLVABLE_CONFLICTS'
                   Title = $pr.title
               })
           }
       }
   }
   ```

2. **Add comment threshold check** (after line 1298):

   ```powershell
   # Check for unaddressed comments threshold even without CHANGES_REQUESTED
   if (-not $hasChangesRequested -and ($isAgentControlledBot -or $isBotReviewer)) {
       $unaddressedCount = ($unacked | Measure-Object).Count
       if ($unaddressedCount -ge 5) {
           Write-Log "PR #$($pr.number): $unaddressedCount unaddressed comments exceed threshold -> /pr-review" -Level WARN
           $null = $results.ActionRequired.Add(@{
               PR = $pr.number
               Author = $authorLogin
               Reason = 'UNADDRESSED_COMMENTS'
               Title = $pr.title
               Category = 'agent-controlled'
               Action = "/pr-review via pr-comment-responder ($unaddressedCount comments)"
           })
       }
   }
   ```

3. **Add synthesizer logic** (after line 1298):

   ```powershell
   # Synthesizer mode: rjmurillo-bot as reviewer on mention-triggered bot PR
   if ($isBotReviewer -and $botInfo.Category -eq 'mention-triggered' -and $hasChangesRequested) {
       $otherBotComments = @($comments | Where-Object {
           $_.user.type -eq 'Bot' -and
           $_.user.login -ne 'rjmurillo-bot' -and
           $_.user.login -ne $authorLogin -and
           $_.reactions.eyes -eq 0
       })

       if ($otherBotComments.Count -gt 0) {
           Write-Log "PR #$($pr.number): Synthesizer mode - $($otherBotComments.Count) comments from other bots" -Level ACTION
           $null = $results.ActionRequired.Add(@{
               PR = $pr.number
               Author = $authorLogin
               Reason = 'SYNTHESIS_REQUIRED'
               Title = $pr.title
               Category = 'synthesizer'
               Action = "Aggregate feedback and mention $($botInfo.Mention)"
           })
       }
   }
   ```

## Approval Conditions

Protocol specification MUST address:

1. **Conflict resolution authority** - document bot author's full authority
2. **Comment threshold** - define when unaddressed comments trigger action
3. **Synthesizer role** - define activation, behavior, format

Implementation MUST update:

1. **Conflict blocking** - bot-authored PRs to ActionRequired (not Blocked)
2. **Comment threshold** - check unaddressed count even without CHANGES_REQUESTED
3. **Synthesizer detection** - add logic for reviewer on mention-triggered bot PRs

## Impact Analysis Review

Not applicable - no impact analysis present.

## Verified Facts (exact values, not summaries)

| Fact | Value | Source |
|------|-------|--------|
| PRs wrongly blocked | #365, #353, #301, #255, #235 | User context |
| All authored by | rjmurillo-bot | User context |
| Block reason | UNRESOLVABLE_CONFLICTS | User context |
| PRs with unaddressed comments | #365, #353, #301, #255, #235 | User context |
| Unaddressed comment counts | 20+ per PR | User context |
| reviewDecision status | NOT "CHANGES_REQUESTED" | User context |
| Synthesizer scenario PR | #247 | User context |
| PR #247 author | copilot-swe-agent | User context |
| rjmurillo-bot role on #247 | REVIEWER | User context |
| Other bots on #247 | coderabbitai, cursor[bot] | User context |
| PR #247 status | CHANGES_REQUESTED | User context |
| Protocol lines for triggers | 133-140 | bot-author-feedback-protocol.md |
| Implementation conflict logic | 1359-1372 | Invoke-PRMaintenance.ps1 |
| Implementation comment ack | 1290-1298 | Invoke-PRMaintenance.ps1 |
| Implementation CHANGES_REQUESTED check | 1262, 1273 | Invoke-PRMaintenance.ps1 |
| Auto-resolvable files | .agents/HANDOFF.md, .agents/sessions/* | Lines 798-808 |
| Eyes reaction protocol | Lines 189-202 | bot-author-feedback-protocol.md |

## Numeric Data

- Unaddressed comments per PR: 20+ (average across 5 PRs)
- Recommended comment threshold: 5 (proposed)
- PRs affected by each gap:
  - Conflict gap: 5 PRs (#365, #353, #301, #255, #235)
  - Comment gap: 5 PRs (same set)
  - Synthesizer gap: 1 PR (#247)
