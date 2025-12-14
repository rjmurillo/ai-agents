# Explainer: Copilot Response Pattern Handling

## Introduction/Overview

The pr-comment-responder agent currently handles standard GitHub review comment workflows but does not account for Copilot's unique response behavior. When you reply to a @Copilot review comment (e.g., to explain why a suggestion is invalid), Copilot does not reply inline to the thread. Instead, Copilot:

1. Creates a **separate follow-up PR** branched from the current PR
2. Posts the response asan **issue comment** on the original PR (not a review comment reply)
3. Links to the follow-up PR in that issue comment

This creates orphaned conversations and unnecessary follow-up PRs that clutter the repository when Copilot's original suggestion was a false positive.

**Problem Statement**: After explaining to Copilot that no action is required, the agent has no way to:
- Detect Copilot's response (because it appears as an issue comment, not a review reply)
- Identify the follow-up PR that Copilot created
- Close the unnecessary follow-up PR
- Mark the original conversation as resolved

## Goals

1. **Detect Copilot Responses**: Poll issue comments after replying to @Copilot to find Copilot's actual response
2. **Parse Response Intent**: Determine whether Copilot agrees (no action needed) or disagrees (created a fix)
3. **Manage Follow-up PRs**: Automatically close follow-up PRs when the original issue was a false positive
4. **Resolve Conversations**: Properly close the loop on review comment threads
5. **Support Polling Strategy**: Implement configurable polling with timeout for Copilot's response

## Non-Goals (Out of Scope)

- Modifying how we respond to non-Copilot reviewers (existing behavior unchanged)
- Automatically merging Copilot's follow-up PRs (manual review required for actual fixes)
- Handling other AI reviewer bots (CodeRabbit, etc.) - this is Copilot-specific
- Real-time webhooks or event-driven responses (polling approach only for initial implementation)
- Modifying Copilot's behavior itself

## User Stories

### US-1: Detect Copilot Response in Issue Comments
**As a** developer using the pr-comment-responder agent,
**I want** the agent to check issue comments after replying to @Copilot,
**So that** I can see Copilot's actual response even though it does not reply in the review thread.

**Acceptance Criteria:**
- Agent polls `gh api repos/{owner}/{repo}/issues/{pr}/comments` after replying to @Copilot
- Agent filters comments to find those authored by `github-actions[bot]` or `copilot` after our reply timestamp
- Agent extracts the response content for further processing
- Polling timeout is configurable (default: 60 seconds, interval: 5 seconds)

### US-2: Identify Follow-up PRs Created by Copilot
**As a** developer using the pr-comment-responder agent,
**I want** the agent to identify when Copilot creates a follow-up PR,
**So that** I know which PR to evaluate or close.

**Acceptance Criteria:**
- Agent parses Copilot's issue comment to extract linked PR numbers
- Agent validates the linked PR exists and was created by Copilot
- Agent retrieves basic metadata about the follow-up PR (title, branch, changes)
- Agent stores the relationship: original PR -> follow-up PR mapping

### US-3: Close Unnecessary Follow-up PRs
**As a** developer using the pr-comment-responder agent,
**I want** the agent to close Copilot's follow-up PRs when no action was required,
**So that** the repository does not accumulate unnecessary open PRs.

**Acceptance Criteria:**
- Agent evaluates if our reply indicated "no action required" or "false positive"
- Agent closes the follow-up PR with an explanatory comment
- Comment includes reference to original conversation explaining why closed
- Agent does NOT close PRs if our reply acknowledged the issue needed fixing

### US-4: Report Copilot Interaction Results
**As a** developer using the pr-comment-responder agent,
**I want** a summary of Copilot interactions in the output,
**So that** I can verify the agent handled responses correctly.

**Acceptance Criteria:**
- Output includes a "Copilot Interactions" section
- Shows: original comment, our reply, Copilot's response, action taken
- Indicates if follow-up PR was closed and why
- Logs any failures (timeout waiting for response, parse errors)

## Functional Requirements

### FR-1: Issue Comment Retrieval
The system must retrieve issue comments using:
```bash
gh api repos/{owner}/{repo}/issues/{pr_number}/comments
```
Note: Issue comments are accessed via the issues endpoint, not the pulls endpoint.

### FR-2: Copilot Response Detection
The system must identify Copilot responses by:
- Author login matching `copilot` or `github-actions[bot]` with Copilot attribution
- Comment timestamp being after our reply timestamp
- Comment body containing patterns indicating it is a response to our reply

### FR-3: Follow-up PR Detection
The system must parse Copilot's issue comments to extract follow-up PR references using patterns such as:
- "I've addressed this in #XX"
- "Created PR #XX"
- URLs matching `github.com/{owner}/{repo}/pull/{number}`
- Markdown links to pull requests

### FR-4: Follow-up PR Closure
The system must close follow-up PRs using:
```bash
gh pr close {follow_up_pr_number} --repo {owner}/{repo} --comment "Closing: original suggestion was a false positive. See PR #{original_pr}."
```

### FR-5: Response Categorization
The system must categorize our replies to determine appropriate follow-up action:
- **No Action Required**: Keywords like "false positive", "not applicable", "correct as-is", "intentional"
- **Acknowledged**: Keywords like "good catch", "fixed", "will address"
- **Needs Discussion**: Keywords like "clarify", "question", "unsure"

### FR-6: Polling Strategy
The system must implement a polling strategy:
- Default timeout: 60 seconds
- Polling interval: 5 seconds
- Maximum attempts: 12
- Early exit: Stop polling when Copilot response is detected

### FR-7: Idempotency
The system must not close the same follow-up PR twice. It should:
- Check PR state before attempting closure
- Skip already-closed PRs
- Log that PR was already handled

## Design Considerations

### Workflow Addition

Add a new **Phase 4: Copilot Follow-up Handling** after Phase 3 (Response Strategy):

```text
Phase 3: Response Strategy
    |
    v
[Is comment from @Copilot?] --No--> End
    |
   Yes
    v
Phase 4: Copilot Follow-up Handling
    |
    v
Poll for Copilot's issue comment response
    |
    v
[Response found?] --No (timeout)--> Log warning, End
    |
   Yes
    v
Parse for follow-up PR reference
    |
    v
[Follow-up PR exists?] --No--> End (conversation complete)
    |
   Yes
    v
[Our reply = "no action"?] --No--> Log: manual review needed
    |
   Yes
    v
Close follow-up PR with explanation
    |
    v
End
```

### Output Format Extension

Extend the existing output format:

```markdown
## PR Comment Response Summary

### Comments Addressed
| Comment | Author | Action | Commit/Response |
|---------|--------|--------|-----------------|
| [summary] | @author | Fixed/Declined | abc123 / [reason] |

### Copilot Interactions
| Original Comment | Our Reply | Copilot Response | Follow-up PR | Action Taken |
|-----------------|-----------|------------------|--------------|--------------|
| "Docs missing" | "False positive, docs exist at /docs" | Created PR #58 | #58 | Closed |

### Commits Pushed
- `abc123` - [description]

### Pending Discussion
- [Any comments needing further input]
```

## Technical Considerations

### API Endpoints Required

1. **Issue Comments** (read): `GET /repos/{owner}/{repo}/issues/{issue_number}/comments`
2. **PR State** (read): `GET /repos/{owner}/{repo}/pulls/{pull_number}`
3. **Close PR** (write): `PATCH /repos/{owner}/{repo}/pulls/{pull_number}` with `state: closed`
4. **PR Comment** (write): `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

### Rate Limiting

- Polling introduces additional API calls (up to 12 per Copilot comment)
- Consider caching previous issue comments to reduce calls
- Use conditional requests with ETags where possible

### Error Handling

Handle these error cases gracefully:
- Timeout waiting for Copilot response (log warning, continue)
- Follow-up PR already closed (skip, log info)
- API rate limit exceeded (back off, retry)
- Malformed Copilot response (log warning, skip follow-up handling)
- Permission denied closing PR (log error, notify user)

### Dependencies

- GitHub CLI (`gh`) version 2.x or later
- Repository permissions: write access to close PRs
- Network connectivity for polling

## Success Metrics

1. **False Positive PR Closure Rate**: Percentage of unnecessary follow-up PRs automatically closed
2. **Response Detection Rate**: Percentage of Copilot responses successfully detected within timeout
3. **Time Saved**: Reduction in manual PR cleanup time
4. **Error Rate**: Percentage of failed closure attempts or missed responses

## Open Questions

1. **Q: Should we support auto-merging valid follow-up PRs?**
   - Current recommendation: No, require manual review for actual code changes
   - Rationale: Risk of merging incorrect fixes is too high

2. **Q: What if Copilot creates multiple follow-up PRs?**
   - Current recommendation: Handle all linked PRs with the same logic
   - Need to verify Copilot's actual behavior in this scenario

3. **Q: Should we resolve the original review thread programmatically?**
   - Current recommendation: Investigate if GitHub API supports resolving conversations
   - Fallback: Leave a comment indicating the issue is resolved

4. **Q: How do we handle the case where Copilot's follow-up PR has already been reviewed/approved?**
   - Current recommendation: Do not close PRs with existing reviews
   - Add check for review state before closing

5. **Q: What is the exact author identifier for Copilot responses?**
   - Need to verify: Is it `copilot`, `github-copilot`, or `github-actions[bot]`?
   - Action: Capture actual response from PR #57 interactions

## Appendix: Example API Responses

### Issue Comment from Copilot (Expected Format)
```json
{
  "id": 12345,
  "user": {
    "login": "copilot",
    "type": "Bot"
  },
  "body": "I've addressed this feedback in #58.\n\nChanges made:\n- Updated documentation references",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Follow-up PR (Expected Format)
```json
{
  "number": 58,
  "title": "Address feedback from PR #57",
  "state": "open",
  "user": {
    "login": "copilot"
  },
  "head": {
    "ref": "copilot/fix-57-docs"
  },
  "base": {
    "ref": "feature-branch"
  }
}
```

---

## Handoff

**Next Steps:**
1. Hand off to **critic** agent for PRD validation
2. After validation, hand off to **task-generator** agent for atomic task breakdown
3. Implementation by **implementer** agent following task breakdown
