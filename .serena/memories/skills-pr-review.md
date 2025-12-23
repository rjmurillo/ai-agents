# PR Review Skills

**Consolidated**: 2025-12-23
**Sources**: skills-pr-review, pr-comment-responder-skills, pr-review-noise-skills

Comprehensive guide for GitHub PR review workflows, bot comment triage, and conversation resolution.

---

## Part 1: Core PR Workflow

### Skill-PR-Review-001: Conversation Resolution Requirement

**Statement**: Before merging, ALL review conversations MUST be resolved. Unresolved threads block merge due to branch protection.

**Atomicity**: 95% | **Impact**: 9/10 | **Validated**: 3

**Query unresolved threads** (GraphQL only - `gh pr view` doesn't support reviewThreads):

```bash
gh api graphql -f query='query($owner: String!, $repo: String!, $number: Int!) { repository(owner: $owner, name: $repo) { pullRequest(number: $number) { reviewThreads(first: 100) { nodes { id isResolved path comments(first: 3) { nodes { id body author { login } } } } } } } }' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER
```

---

### Skill-PR-Review-002: Conversation Resolution Protocol

**Statement**: Reply with resolution details, THEN mark resolved. Pushing fixes alone does NOT resolve.

**Atomicity**: 98% | **Impact**: 10/10 | **Tag**: critical

**Protocol** - Reply with ONE of:

1. **Fix applied**: `Fixed in commit abc1234. [Brief description]`
2. **Won't fix**: `Won't fix: [Rationale for different approach]`
3. **Action required**: `@reviewer Could you clarify [question]?`

**Then resolve**:

```bash
# Reply to thread
gh api graphql -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' -f id="PRRT_xxx" -f body="Reply"

# Resolve thread
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"
```

---

### Skill-PR-Review-003: API Selection (REST vs GraphQL)

**Statement**: REST for simple replies with comment IDs; GraphQL for thread resolution or thread IDs.

**Atomicity**: 94% | **Impact**: 8/10

| ID Type | Format | API |
|---------|--------|-----|
| Comment ID | Numeric `2616639895` | REST `in_reply_to` |
| Thread ID | `PRRT_kwDO...` | GraphQL mutations |

**Decision Matrix**:

| Need | Use |
|------|-----|
| Simple reply, have comment ID | REST |
| Need to resolve thread | GraphQL (only option) |
| Have thread ID only | GraphQL |

---

## Part 2: Bot Reviewer Triage

### Skill-PR-006: Reviewer Signal Quality

**Statement**: Prioritize reviewers by historical actionability rate.

**Atomicity**: 96% | **Validated**: 14 PRs

| Priority | Reviewer | Signal Rate | Action |
|----------|----------|-------------|--------|
| **P0** | cursor[bot] | **100%** (28/28) | Process immediately |
| **P1** | Human reviewers | N/A | Domain expertise |
| **P2** | coderabbitai[bot] | ~50% (163 comments) | Review carefully |
| **P3** | Copilot | ~34% (459 comments) | Skim for real issues |
| **P4** | gemini-code-assist[bot] | ~25% (49 comments) | Quick scan |

**Comment Type Actionability**:

| Type | Rate | Examples |
|------|------|----------|
| Bug reports | ~90% | cursor[bot] bugs, type errors |
| Missing coverage | ~70% | Test gaps, edge cases |
| Style suggestions | ~20% | Formatting, naming |
| Summaries | 0% | CodeRabbit walkthroughs |

---

### Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate ALL reviewers before triaging to avoid single-bot blindness.

**Atomicity**: 92% | **Validated**: 2

```bash
gh pr view PR --json reviews --jq '.reviews[].author.login' | sort -u
```

---

### Skill-PR-002: Independent Comment Parsing

**Statement**: Parse each comment independently; same-file comments may address different issues.

**Atomicity**: 88%

---

### Skill-PR-003: Verification Count

**Statement**: Verify addressed_count matches total_comment_count before claiming completion.

**Atomicity**: 94% | **Validated**: 2

---

## Part 3: Acknowledgment Protocol

### Skill-PR-Comment-001: Acknowledgment BLOCKING Gate

**Statement**: Phase 3 BLOCKED until eyes reaction count equals comment count.

**Atomicity**: 100% | **Tag**: critical

```bash
COMMENT_COUNT=$(gh api repos/O/R/pulls/PR/comments --jq 'length')
EYES_COUNT=$(gh api repos/O/R/pulls/PR/comments --jq '[.[].reactions.eyes] | add')
[ "$EYES_COUNT" -lt "$COMMENT_COUNT" ] && echo "BLOCKED" && exit 1
```

---

### Skill-PR-Comment-002: Session-Specific Work Tracking

**Statement**: Track 'NEW this session' separately from 'DONE prior sessions'.

**Atomicity**: 100% | **Tag**: critical

**Anti-Pattern**: Conflating prior session replies with current session obligations.

---

### Skill-PR-Comment-003: API Verification Before Phase Completion

**Statement**: Verify mandatory step completion via API before marking phase complete.

**Atomicity**: 100% | **Tag**: critical

---

### Skill-PR-Comment-004: PowerShell Fallback to gh CLI

**Statement**: PowerShell script failure requires immediate gh CLI fallback attempt.

**Atomicity**: 100%

```bash
if ! pwsh Add-CommentReaction.ps1 -CommentId $ID -Reaction "eyes"; then
  gh api repos/O/R/pulls/comments/$ID/reactions -X POST -f content="eyes"
fi
```

---

## Part 4: Security Priority

### Skill-PR-Review-Security-001: Security Comment Triage

**Statement**: Security-domain comments receive +50% triage priority.

**Atomicity**: 94% | **Impact**: 7/10

| Domain | Keywords | Adjustment |
|--------|----------|------------|
| Security | CWE, vulnerability, injection | +50% - Always investigate |
| Bug | error, crash | No change |
| Style | formatting | No change |

---

### Skill-Triage-002: Never Dismiss Security Without Process Analysis

**Statement**: Before dismissing security suggestion, verify protection covers all process boundaries.

**Atomicity**: 93%

**Checklist**:
- [ ] Protection covers ALL execution paths?
- [ ] Protection in same process as action?
- [ ] TOCTOU analysis done?
- [ ] Conditional execution checked?

---

## Part 5: Known False Positives

### Skill-Review-001: CodeRabbit Sparse Checkout Blindness

**Statement**: CodeRabbit flags .agents/ files as missing due to sparse checkout pattern.

**Atomicity**: 95%

**Verify**: `git ls-tree HEAD .agents/`

---

### Skill-Review-002: Python Implicit String Concat

**Statement**: Dismiss Python implicit string concat warnings as false positives.

**Atomicity**: 92%

Adjacent string literals `r"pattern1" r"pattern2"` are valid Python per PEP 3126.

---

### Copilot False Positive Patterns

| Pattern | Frequency | Actionability |
|---------|-----------|---------------|
| Unused variable | ~30% | ~20% (often intentional) |
| Style suggestions | ~25% | ~10% (noise) |
| Syntax issues | ~10% | ~90% (usually valid) |

---

### gemini-code-assist False Positives

| Pattern | Frequency | Actionability |
|---------|-----------|---------------|
| Documentation-as-code | ~40% | 0% (misunderstands docs) |
| Style suggestions | ~30% | ~20% |

---

## Part 6: Copilot Follow-Up PR Detection

### Skill-PR-Copilot-001: Follow-Up PR Pattern

**Statement**: Detect Copilot follow-up PRs using branch pattern `copilot/sub-pr-{original}`.

**Atomicity**: 96%

**Categories**:

| Category | Indicator | Action |
|----------|-----------|--------|
| DUPLICATE | No/minimal changes | Close with commit ref |
| SUPPLEMENTAL | Additional issues | Evaluate for merge |
| INDEPENDENT | Unrelated | Close with explanation |

---

## Application Checklist

### Phase 1-2: Context and Acknowledgment

- [ ] Enumerate ALL reviewers (Skill-PR-001)
- [ ] Prioritize cursor[bot] first (Skill-PR-006)
- [ ] Parse each comment independently (Skill-PR-002)
- [ ] **BLOCKING**: Add eyes reaction to EACH comment
- [ ] **BLOCKING**: Verify eyes_count == comment_count via API

### Phase 3-5: Analysis and Response

- [ ] Track 'NEW this session' vs 'DONE prior sessions'
- [ ] For atomic bugs, use Quick Fix path
- [ ] Use correct API (REST vs GraphQL)
- [ ] Reply then resolve each thread

### Phase 6-8: Verification

- [ ] Check for Copilot follow-up PRs
- [ ] Verify addressed_count == total_comment_count
- [ ] Update HANDOFF.md with session summary

---

## Cumulative Metrics (as of 2025-12-22)

| Reviewer | Total Comments | Signal Rate | Trend |
|----------|----------------|-------------|-------|
| cursor[bot] | 45 | **100%** | ✅ Stable |
| Copilot | 459 | ~34% | ↓ Declining |
| coderabbitai[bot] | 164 | ~49% | → Stable |
| gemini-code-assist[bot] | 49 | ~25% | → Stable |
