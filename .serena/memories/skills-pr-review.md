# PR Review Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/2025-12-14-pr-comment-responder-gaps.md`

## Skill-PR-001: Enumerate All Reviewers

**Statement**: Enumerate all reviewers (gh pr view --json reviews) before triaging to avoid single-bot blindness

**Context**: PR comment response workflow

**Evidence**: PR #32 - Agent counted only Copilot (5 comments) when CodeRabbit also posted (2 comments)

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Implementation**:

```bash
# Always enumerate ALL review sources first
gh pr view $PR_NUMBER --json reviews,comments | jq '.reviews[].author.login, .comments[].author.login' | sort -u
```

**Anti-Pattern**:

- Assuming only one reviewer (Copilot OR CodeRabbit)
- Not checking for comments from multiple bots
- Hardcoding reviewer name assumptions

---

## Skill-PR-002: Parse Comments Independently

**Statement**: Parse each comment body independently; do not aggregate or deduplicate by file path

**Context**: PR comment triage and response

**Evidence**: r2617109424 and r2617109432 both on claude/orchestrator.md with different concerns - one was missed

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Implementation**:

1. Retrieve all comments as individual items
2. Process each comment ID independently
3. Track addressed status per comment ID, not per file
4. Multiple comments on same file = multiple items to address

---

## Skill-PR-003: Verify Comment Count Before Done

**Statement**: Verify `comments_addressed == total_comments` before claiming PR review complete

**Context**: PR comment response completion check

**Evidence**: Agent claimed "All 5 comments addressed" when 7 review comments existed

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 10/10

**Implementation**:

```bash
# Before claiming done, verify counts match
TOTAL=$(gh pr view $PR_NUMBER --json reviewComments | jq '.reviewComments | length')
ADDRESSED=$(grep -c "RESOLVED" response-tracking.md)
if [ "$ADDRESSED" -ne "$TOTAL" ]; then
    echo "ERROR: Only $ADDRESSED/$TOTAL comments addressed"
    exit 1
fi
```

---

## Related Documents

- Source: `.agents/retrospective/2025-12-14-pr-comment-responder-gaps.md`
- Related: pr-comment-responder-skills (existing memory)
