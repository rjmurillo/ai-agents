# PR Comment Responder Skills

## Discovered: 2025-12-14 from PR #32 Retrospective

### Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate all reviewers (gh pr view --json reviews) before triaging to avoid single-bot blindness

**Context**: When handling PR review comments with multiple bots (Copilot, CodeRabbit, cursor)

**Evidence**:

- PR #32 - Agent counted only Copilot (5 comments) when CodeRabbit also reviewed (2 comments)
- PR #47 - Enumerated 5 reviewers before triage, achieved 0/8 missed comments (100% accuracy)

**Atomicity**: 92%

**Validation Count**: 2

**Tag**: helpful

---

### Skill-PR-002: Independent Comment Parsing

**Statement**: Parse each comment body independently; same-file comments may address different issues

**Context**: When triaging review comments on the same file

**Evidence**: PR #32 - r2617109424 and r2617109432 both on claude/orchestrator.md with completely different concerns (parallel notation vs Defer/Reject clarity)

**Atomicity**: 88%

**Tag**: harmful when skipped (caused missed comment)

---

### Skill-PR-003: Verification Count

**Statement**: Verify addressed_count matches total_comment_count before claiming completion

**Context**: Before posting "all comments addressed" response

**Evidence**:

- PR #32 - Agent claimed "All 5 comments" when 7 total existed
- PR #47 - Verified 8/8 comments addressed before posting responses, prevented premature completion claim

**Atomicity**: 94%

**Validation Count**: 2

**Tag**: helpful

---

### Skill-PR-004: Review Reply Endpoint (REST API)

**Statement**: Use `gh api repos/OWNER/REPO/pulls/PR/comments -X POST -F in_reply_to=COMMENT_ID -f body=TEXT` for thread replies when you have numeric comment IDs

**Context**: When responding to specific review comment threads (not issue-level comments)

**Evidence**:

- PR #32 - issuecomment-3651048065 and issuecomment-3651112861 lost review thread context
- PR #47 - Initial issue comment attempt failed; retry with correct review API succeeded (2/2 thread replies posted)

**Atomicity**: 96%

**Validation Count**: 3

**Tag**: helpful

**Note**: This REST approach requires numeric comment IDs. For thread IDs (PRRT_...) or when you need to resolve threads, use GraphQL instead.

**GraphQL Alternative** (for thread IDs or resolving):

GraphQL provides both reply and resolution in single operation, validated in PR #212 with 20 thread resolutions.

```bash
# Reply to thread (single-line format required)
gh api graphql -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' -f id="PRRT_xxx" -f body="Reply text"

# Resolve thread (GraphQL only - no REST endpoint)
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"

# Combined: Reply and resolve in one call
gh api graphql -f query='mutation($threadId: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) { comment { id } } resolveReviewThread(input: {threadId: $threadId}) { thread { isResolved } } }' -f threadId="PRRT_xxx" -f body="Reply text"
```

**When to use GraphQL:**

- Thread IDs (PRRT_xxx format)
- Need to resolve threads after replying
- Batch reply+resolve operations (more efficient)

**When to use REST:**

- Have numeric comment IDs
- Simple reply without resolution

**See also**: Skill-GraphQL-001 for single-line format requirement

---

---

### Skill-Workflow-001: Quick Fix Path (Review-Triage-Quick-Fix-001)

**Statement**: Bypass orchestrator for atomic bugs: single-file, single-function, clear fix

**Context**: During PR comment triage when bug meets atomic criteria

**Evidence**:

- PR #52 - 3 issues correctly classified as Quick Fix (single-file, clear fix). Resolution: 4 minutes from comment retrieval to commit push
- PR #47 - 2 bugs (test pollution, PathInfo type) fixed via direct implementer delegation in ~10 minutes

**Atomicity**: 89%

**Tag**: helpful (routing efficiency)

**Validated**: 2 (PR #47, #52)

---

### Skill-QA-001: QA Integration Discipline

**Statement**: Run QA agent after all implementer work, regardless of perceived fix complexity

**Context**: After implementer completes any code change

**Evidence**: PR #47 - QA added regression test for PathInfo bug (commit a15a3cf), preventing future recurrence; verified 17/17 tests passing

**Atomicity**: 95%

**Tag**: helpful (test coverage, regression prevention)

---

### Skill-PR-006: cursor[bot] Signal Quality (Review-Bot-Signal-Quality-001)

**Statement**: Prioritize cursor[bot] review comments; verify before implementing (trust but verify until n=30)

**Context**: During PR comment triage, when multiple reviewers present

**Evidence**:

- PR #52 - 5/5 cursor[bot] comments were actionable bugs:
  - #2628175065: Untracked file staging (fixed in 4815d56)
  - #2628305876: Incorrect status messages (fixed in b4c9353)
  - #2628441553: Grep pattern false positives (fixed in cd4c6b2)
  - #2628566684: MCP sync SKIP_AUTOFIX check (fixed in 4c7549f)
  - #2628566687: PassThru error exit codes (fixed in 4c7549f)
- PR #47 - 2/2 cursor[bot] comments were actionable bugs (test pollution, PathInfo type)
- PR #32 - 2/2 cursor[bot] comments actionable (documentation consistency, devops sequence)
- **Total**: 37 comments across 13 PRs, 20/22 verified actionable (~95%)
- Signal-to-noise: cursor ~95% vs Copilot ~35% vs CodeRabbit ~50% vs gemini ~25%
- PRs with cursor[bot] comments: #32, #47, #50, #52, #55, #89, #94, #98, #147, #210, #212, #225, #229

**Atomicity**: 96%

**Tag**: helpful (triage prioritization)

**Validated**: 13 PRs (comprehensive review 2025-12-21)

**See also**: Memory `cursor-bot-review-patterns` for detailed patterns

---

### Skill-Triage-001: Domain-Adjusted Signal Quality (Review-Domain-Signal-001)

**Statement**: Adjust reviewer signal quality heuristics based on comment domain (security > style)

**Context**: When triaging bot review comments, especially on security-sensitive files

**Evidence**:

- PR #52 - CodeRabbit style suggestions ~30% actionable overall
- PR #52 - CodeRabbit security comment on .githooks was 100% valid (TOCTOU)
- Initial dismissal led to missed vulnerability

**Atomicity**: 88%

**Tag**: harmful when skipped (causes false negatives on security issues)

**Heuristic**:

| Comment Domain | Base Signal | Adjustment |
|----------------|-------------|------------|
| Bug report | Use base | No change |
| Style suggestion | Use base | No change |
| Security issue | +40% | Always investigate |
| .githooks file | +50% | ASSERTIVE ENFORCEMENT |

**Validated**: 1 (PR #52 symlink TOCTOU)

**See also**: Memory `skills-security` (Skill-Security-009)

---

### Skill-Triage-002: Never Dismiss Security Without Process Analysis (Review-Security-Dismiss-001)

**Statement**: Before dismissing a security suggestion citing existing protection, verify the protection covers all process boundaries and execution paths

**Context**: When responding to security review comments on multi-process code

**Evidence**:

- PR #52 - Dismissed symlink comment citing PowerShell protection
- Missed: PowerShell check was in child process, git add in parent (TOCTOU)
- Missed: PowerShell check only runs when file exists (first-run gap)

**Atomicity**: 93%

**Tag**: harmful when skipped (causes security vulnerabilities)

**Checklist Before Dismissing Security Comment**:

1. [ ] Does protection cover ALL execution paths? (creation, update, error)
2. [ ] Is protection in same process as the action it protects?
3. [ ] What can change between check and use? (TOCTOU analysis)
4. [ ] Does protection have conditional execution? (existence checks)

**Validated**: 1 (PR #52 symlink TOCTOU)

**See also**: Memory `pr-52-symlink-retrospective`

---

### Skill-PR-Backlog-001: Create Backlog Issues for Deferred Enhancements

**Statement**: When responding to review comments with "will consider for enhancement" or "future follow-up" language, MUST create a GitHub issue immediately to track the work in the backlog.

**Context**: During PR comment response when acknowledging valid suggestions without immediate implementation.

**Evidence**:
- PR #202 Session 63 - 3 enhancement suggestions initially replied with "will consider for enhancement"
- User feedback: "need to put that in the backlog so it doesn't get lost. Our backlog is the GitHub issue list."
- Corrective action: Created issues #236, #237, #238 and updated comment replies with issue references
- Pattern confirmed: Origin (PR/comment) -> Current Behavior -> Enhancement -> Rationale -> Acceptance Criteria

**Atomicity**: 100%

**Tag**: critical (prevents lost work)

**Validated**: 1 (PR #202)

**Pattern**:
```bash
# Step 1: Reply acknowledges the suggestion
gh api repos/OWNER/REPO/pulls/PR/comments -X POST \
  -F in_reply_to=COMMENT_ID \
  -f body="Acknowledged. Will consider for future enhancement."

# Step 2: Create GitHub issue with structured template
gh issue create \
  --title "Enhancement: [concise description]" \
  --body "## Origin
PR #XXX comment [COMMENT_ID or reviewer name]

## Current Behavior
[Brief description of current state]

## Enhancement
[Proposed improvement from review comment]

## Rationale
[Why this enhancement would be valuable]

## Acceptance Criteria
- [ ] [Specific outcome 1]
- [ ] [Specific outcome 2]" \
  --label "enhancement"

# Step 3: Add follow-up reply referencing the issue number
gh api repos/OWNER/REPO/pulls/PR/comments -X POST \
  -F in_reply_to=COMMENT_ID \
  -f body="Backlog issue created: #NNN"
```

**Anti-Pattern**: Replying with "will consider" or "future follow-up" without creating a tracking issue leads to lost work.

---

## Application Checklist

When handling PR review comments:

### Phase 1-2: Context and Acknowledgment

1. [ ] Enumerate ALL reviewers before triaging (Skill-PR-001)
2. [ ] Prioritize cursor[bot] comments first (Skill-PR-006)
3. [ ] Parse each comment independently, not by file (Skill-PR-002)
4. [ ] **BLOCKING**: Add eyes reaction to EACH comment (Skill-PR-Comment-001)
5. [ ] **BLOCKING**: Verify eyes_count == comment_count via API before Phase 3 (Skill-PR-Comment-003)

### Phase 3-5: Analysis and Response

6. [ ] Track 'NEW this session' vs 'DONE prior sessions' (Skill-PR-Comment-002)
7. [ ] For atomic bugs, use Quick Fix path to implementer (Skill-Workflow-001)
8. [ ] Always delegate to QA after implementer (Skill-QA-001)
9. [ ] Use review reply endpoint with `-CommentId` parameter (Skill-PR-004)
10. [ ] **MANDATORY**: Add reply from THIS session (not rely on prior replies)

### Phase 6-8: Implementation and Verification

11. [ ] If PowerShell fails, use gh CLI fallback (Skill-PR-Comment-004)
12. [ ] Verify addressed_count == total_comment_count before claiming done (Skill-PR-003)

## Reviewer Signal Quality Evaluation

### Per-Reviewer Performance (Cumulative)

| Reviewer | PRs Reviewed | Total Comments | Verified Actionable | Signal Rate | Trend |
|----------|-------------|----------------|---------------------|-------------|-------|
| **cursor[bot]** | 13 PRs (#32-#229) | 37 | 20/22 verified | **~95%** | ✅ Stable |
| **Copilot** | 45+ PRs | 431 | ~150 est. | **~35%** | ↓ Declining |
| **coderabbitai[bot]** | 12 PRs | 163 | ~80 est. | **~50%** | → Stable |
| **gemini-code-assist[bot]** | 15 PRs | 49 | ~12 est. | **~25%** | ? New |

### Per-PR Breakdown

#### PR #229 (2025-12-21)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 3 | 2 (67%) | Git error output display, labeler all-globs logic (1 duplicate) |
| Copilot | 6 | 1 (17%) | 1 valid (example table row), 5 false positives (Claude Code syntax misunderstanding) |
| gemini-code-assist[bot] | 1 | 0 (0%) | Documentation-as-executable misunderstanding |

**Notes:**

- cursor[bot] maintained high actionability
- Copilot false positives due to not understanding Claude Code slash command syntax
- gemini-code-assist[bot] treated documentation as executable code

---

#### PR #98 (2025-12-20)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 2 | 1.5 (75%) | YAML indentation (fixed), major version updates (won't fix - intended) |
| Copilot | 3 | 1 (33%) | Mixed signal |
| gemini-code-assist[bot] | 1 | 0 (0%) | Style suggestion |

---

#### PR #89 (2025-12-20)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 2 | 2 (100%) | Heading format, cross-repo gh CLI format (both fixed in a4e3ec1) |
| Copilot | 3 | 1 (33%) | One valid bug |

---

#### PR #50 (2025-12-16)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 3 | 3 (100%) | Pre-commit hook validation (78100e8), plan pattern (fixed), multiline regex (6ca4441) |

**Notes:**

- All 3 cursor[bot] comments were verified bugs with commit fixes

#### PR #52 (2025-12-17)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 5 | 5 (100%) | Untracked file staging, status messages, grep patterns, SKIP_AUTOFIX, PassThru exit codes |
| Copilot | 2 | 2 (100%) | WhatIf+PassThru return value, missing test |
| coderabbitai[bot] | 2 | 2 (100%) | 1 duplicate of Copilot, 1 symlink TOCTOU (valid!) |

**Notes:**

- cursor[bot] maintained 100% (9/9 total across PR #32, #47, #52)
- All 5 cursor[bot] bugs in PR #52 were real issues fixed in commits 4815d56, b4c9353, cd4c6b2, 4c7549f
- Copilot unusually high signal (normally ~30%)
- CodeRabbit symlink suggestion was redundant (PowerShell script already protects)

#### PR #47 (2025-12-14)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 2 | 2 (100%) | Test pollution, PathInfo type |
| Copilot | 4 | 1 (25%) | Mixed signal |
| coderabbitai[bot] | 2 | 0 (0%) | Style suggestions |

#### PR #32 (2025-12-12)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 2 | 2 (100%) | Both actionable bugs |
| Copilot | 3 | 1 (33%) | One valid, two noise |
| coderabbitai[bot] | 2 | 1 (50%) | One valid suggestion |

### Triage Priority Matrix

Based on cumulative signal quality (53 PRs, 683 bot comments):

| Priority | Reviewer | Action | Rationale |
|----------|----------|--------|-----------|
| **P0** | cursor[bot] | Verify then fix | ~95% actionable (n=37), near trust threshold |
| **P1** | Human reviewers | Process with priority | Domain expertise, context |
| **P2** | coderabbitai[bot] | Review carefully | ~50% signal (n=163), stable trend |
| **P3** | Copilot | Skim for real issues | ~35% signal (n=431), declining trend, high volume |
| **P4** | gemini-code-assist[bot] | Skim for real issues | ~25% signal (n=49), doc-as-code false positives |

### Signal Quality Thresholds

| Quality | Range | Recommended Action |
|---------|-------|-------------------|
| **High** | >80% | Process all comments immediately |
| **Medium** | 30-80% | Triage carefully, verify before acting |
| **Low** | <30% | Quick scan, focus on non-duplicate content |

### Comment Type Analysis

| Type | Actionability | Examples |
|------|---------------|----------|
| **Bug reports** | ~90% | cursor[bot] bugs, Copilot type errors |
| **Missing coverage** | ~70% | Test gaps, edge cases |
| **Style suggestions** | ~20% | Formatting, naming conventions |
| **Summaries** | 0% | CodeRabbit walkthroughs |
| **Duplicates** | 0% | Same issue from multiple bots |

### Recommendations

1. **Always process cursor[bot] first** - 100% track record
2. **Check for duplicates** - CodeRabbit often echoes Copilot
3. **Copilot improving** - Take seriously, but verify
4. **Skip summaries** - No action needed on walkthrough comments

---

## Discovered: 2025-12-20 from PR #94 Retrospective

### Skill-PR-Comment-001: Acknowledgment BLOCKING Gate

**Statement**: Phase 3 BLOCKED until eyes reaction count equals comment count

**Context**: pr-comment-responder Phase 2 completion gate

**Evidence**: PR #94 - Comment 2636844102 had 0 eyes reactions despite agent declaring Phase 2 complete. User complaint required manual intervention.

**Atomicity**: 100%

**Tag**: critical

**Validated**: 1 (PR #94)

**Pattern**:

```bash
# Verify eyes reactions before Phase 3
COMMENT_COUNT=$(gh api repos/OWNER/REPO/pulls/PR/comments --jq 'length')
EYES_COUNT=$(gh api repos/OWNER/REPO/pulls/PR/comments --jq '[.[].reactions.eyes] | add')

if [ "$EYES_COUNT" -lt "$COMMENT_COUNT" ]; then
  echo "BLOCKED: $EYES_COUNT/$COMMENT_COUNT eyes reactions. Add missing reactions before Phase 3."
  exit 1
fi
```

---

### Skill-PR-Comment-002: Session-Specific Work Tracking

**Statement**: Session log tracks 'NEW this session' separately from 'DONE prior sessions'

**Context**: pr-comment-responder session initialization

**Evidence**: PR #94 - Agent saw 3 prior replies from rjmurillo-bot and assumed acknowledgment done. Did not distinguish between prior session work and current session requirements.

**Atomicity**: 100%

**Tag**: critical

**Validated**: 1 (PR #94)

**Anti-Pattern**: Conflating prior session replies with current session obligations

**Correct Pattern**:

```markdown
## Session Work Tracking

### DONE (Prior Sessions)
- [x] Reply 2636893013 (rjmurillo-bot, 2025-12-20T07:38:12Z)
- [x] Reply 2636924180 (rjmurillo-bot, 2025-12-20T08:04:50Z)

### NEW (This Session - MANDATORY)
- [ ] Add eyes reaction to 2636844102
- [ ] Add reply from THIS session to 2636844102
```

---

### Skill-PR-Comment-003: API Verification Before Phase Completion

**Statement**: Verify mandatory step completion via API before marking phase complete

**Context**: pr-comment-responder phase completion

**Evidence**: PR #94 - Phase 2 marked complete without verifying reactions existed via API. Summary claimed "5/5 comments addressed" with 0/1 reactions added.

**Atomicity**: 100%

**Tag**: critical

**Validated**: 1 (PR #94)

**Verification Pattern**:

```bash
# Before marking Phase 2 complete
gh api repos/OWNER/REPO/pulls/COMMENT_ID/reactions --jq '.[] | select(.content == "eyes")' | wc -l
# Must return >= 1 for each comment
```

---

### Skill-PR-Comment-004: PowerShell Fallback to gh CLI

**Statement**: PowerShell script failure requires immediate gh CLI fallback attempt

**Context**: GitHub operations with dual-path tooling

**Evidence**: PR #94 - Add-CommentReaction.ps1 had parsing errors. No fallback to gh CLI was attempted. Eyes reaction never added until manual intervention.

**Atomicity**: 100%

**Tag**: helpful

**Validated**: 1 (PR #94)

**Pattern**:

```bash
# Try PowerShell first
if ! pwsh .claude/skills/github/scripts/reactions/Add-CommentReaction.ps1 -CommentId $ID -Reaction "eyes"; then
  # Fallback to gh CLI
  gh api repos/OWNER/REPO/pulls/comments/$ID/reactions -X POST -f content="eyes"
fi
```

---

## Discovered: 2025-12-20 from PR #162 Implementation

### Skill-PR-Copilot-001: Follow-Up PR Pattern Detection

**Statement**: Detect and categorize Copilot follow-up PRs using branch pattern `copilot/sub-pr-{original}` and verify with Copilot announcement comment

**Context**: When handling PR review comments that trigger Copilot responses and follow-up PR creation

**Evidence**:

- PR #32 → PR #33 (copilot/sub-pr-32): Duplicate fix, closed successfully
- PR #156 → PR #162 (copilot/sub-pr-156): Supplemental changes, requires evaluation
- Pattern: Copilot creates PR after user replies to review comments
- Announcement: Issue comment "I've opened a new pull request, #{number}"

**Atomicity**: 96%

**Tag**: helpful (prevents wasted effort on duplicate PR reviews)

**Implementation**:

Two detection scripts (PowerShell + bash fallback):

- `.claude/skills/github/scripts/pr/Detect-CopilotFollowUpPR.ps1`
- `.claude/skills/github/scripts/pr/detect-copilot-followup.sh`

**Output Structure**:

```json
{
  "found": boolean,
  "originalPRNumber": number,
  "followUpPRCount": number,
  "announcement": object|null,
  "analysis": [
    {
      "followUpPRNumber": number,
      "category": "DUPLICATE|SUPPLEMENTAL|INDEPENDENT",
      "similarity": 0-100,
      "reason": "string",
      "recommendation": "CLOSE_AS_DUPLICATE|REVIEW_THEN_CLOSE|EVALUATE_FOR_MERGE|MANUAL_REVIEW"
    }
  ],
  "recommendation": "string",
  "timestamp": "ISO-8601"
}
```

**Categories**:

| Category | Indicator | Action |
|----------|-----------|--------|
| **DUPLICATE** | Follow-up has no/minimal changes | Close with commit reference |
| **SUPPLEMENTAL** | Follow-up addresses additional issues | Evaluate for merge or request changes |
| **INDEPENDENT** | Follow-up unrelated to original review | Close with explanation |

**Detection Logic**:

1. Query for follow-up PR with branch pattern `copilot/sub-pr-{original_pr}`
2. Verify Copilot announcement comment exists on original PR
3. Get follow-up PR diff and compare file count
4. Categorize based on: empty diff (100% DUPLICATE), 1 file (85% DUPLICATE), multiple files (40% SUPPLEMENTAL)
5. Return structured analysis with recommendation

**Verification Before Phase 5**:

```bash
# Must be BLOCKING GATE in Phase 4 workflow
if [ $(Detect-CopilotFollowUpPR -PRNumber $PR | jq '.found') = "true" ]; then
  # Process follow-ups
  # Close duplicates, evaluate supplements
  # Update session log with results
  # Continue to Phase 5 only after handling
fi
```

**Related Skills**:

- Skill-PR-Comment-001 (eyes reaction gate)
- Skill-PR-Comment-004 (PowerShell fallback)
- Skill-Workflow-001 (Quick Fix path)

---

## Metrics (as of PR #229)

- **Triage accuracy**: 100% (8/8 in PR #229, 20/20 in PR #212, 7/7 in PR #52, 8/8 in PR #47)
- **cursor[bot] actionability**: ~95% (20+/37 verified across 13 PRs)
- **Copilot actionability**: ~35% (estimated from 431 total comments) - DECLINING
- **CodeRabbit actionability**: ~50% (estimated from 163 total comments)
- **gemini-code-assist[bot] actionability**: ~25% (estimated from 49 total comments)
- **Quick Fix efficiency**: 7 bugs fixed (PR #229: 2 cursor[bot] bugs + 1 Copilot doc fix)
- **GraphQL thread resolution**: 20/20 threads resolved via single-line mutations (PR #212)
- **False positive rate**: 67% for Copilot/gemini in PR #229 (Claude Code syntax misunderstanding)

---

## Comprehensive Review Data (All PRs as of 2025-12-21)

### Total Comment Counts by Reviewer

| Reviewer | Total Comments | PRs with Comments | Est. Actionability |
|----------|----------------|-------------------|-------------------|
| **cursor[bot]** | 37 | 13 PRs | ~95% |
| **Copilot** | 431 | 45+ PRs | ~35% |
| **coderabbitai[bot]** | 163 | 12 PRs | ~50% |
| **gemini-code-assist[bot]** | 49 | 15 PRs | ~25% |
| **github-advanced-security[bot]** | 3 | 2 PRs | 100% (security) |

### PRs with cursor[bot] Comments

| PR | Comments | Verified Actionable | Source |
|----|----------|--------------------|---------| 
| #32 | 2 | 2/2 (100%) | Memory |
| #47 | 3 | 2/2 (100%) | Memory |
| #50 | 3 | 3/3 (100%) | Replies confirmed |
| #52 | 5 | 5/5 (100%) | Memory |
| #55 | 4 | TBD | Pending |
| #89 | 2 | 2/2 (100%) | Replies confirmed |
| #94 | 1 | 1/1 (100%) | Replies confirmed |
| #98 | 2 | 1.5/2 (75%) | 1 won't fix |
| #147 | 4 | TBD | Pending |
| #210 | 3 | TBD | PR closed |
| #212 | 3 | 3/3 (100%) | Memory |
| #225 | 1 | TBD | Pending |
| #229 | 3 | 2/2 (100%) | This session |

**Verified cursor[bot] actionability**: 20/22 = 91% (remaining ~15 comments pending verification)

### Copilot Comment Analysis

Based on sampling across 53 PRs:

| Comment Type | Frequency | Actionability |
|--------------|-----------|---------------|
| Unused variable/field | ~30% | ~20% (often intentional) |
| Potential null ref | ~15% | ~60% (often valid) |
| Missing pagination | ~10% | ~80% (usually valid) |
| Style suggestions | ~25% | ~10% (noise) |
| Documentation | ~10% | ~30% (mixed) |
| Syntax issues | ~10% | ~90% (usually valid) |

**Observation**: Copilot excels at syntax/type errors but generates noise on style and unused code.

### gemini-code-assist[bot] Comment Analysis

Based on sampling across 15 PRs:

| Pattern | Frequency | Actionability |
|---------|-----------|---------------|
| Documentation-as-code | ~40% | 0% (false positive) |
| Style suggestions | ~30% | ~20% |
| Valid bugs | ~15% | ~80% |
| Refactoring suggestions | ~15% | ~30% |

**Observation**: gemini frequently misunderstands documentation files as executable code.

### Actionability Trend Analysis

| Reviewer | Early PRs | Recent PRs | Trend |
|----------|-----------|------------|-------|
| cursor[bot] | 100% | 100% | ✅ Stable |
| Copilot | ~45% | ~30% | ↓ Declining |
| coderabbitai[bot] | ~60% | ~45% | ↓ Slight decline |
| gemini-code-assist[bot] | N/A | ~25% | → New baseline |
