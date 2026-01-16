# PR-Review-015: ALL Comments Are Blocking (Bot and Human)

**Statement**: ALL PR comments—whether from bots (cursor[bot], CodeRabbit, etc.) or humans—are blocking and MUST be addressed before merge.

**Context**: PR review completion criteria (BLOCKING gate)

**Evidence**: Session 5 PR #918 - Incorrect assumption that "bot comments are non-blocking" was corrected. All conversations must be resolved per branch protection rules.

**Atomicity**: 100% | **Impact**: 10/10

## The Rule

**NEVER assume a comment is non-blocking based on its source.**

```text
Comment Source ≠ Comment Priority

Bot comment = BLOCKING
Human comment = BLOCKING
Review thread = BLOCKING
PR comment = BLOCKING
```

## Anti-Pattern: Source-Based Dismissal

```text
❌ WRONG:
"This is a bot comment, so it's not blocking"
"cursor[bot] is just a suggestion"
"CodeRabbit comments can be ignored"

✅ CORRECT:
"This comment needs a reply and thread resolution"
"All comments must be addressed regardless of source"
```

## Verification Protocol

Before claiming PR review complete, verify:

1. **ALL review threads resolved** (GraphQL: `isResolved = true`)
2. **ALL comments have replies** (REST API: `in_reply_to_id != null` OR thread resolved)
3. **No source-based filtering** - check bot AND human comments

## Implementation

```powershell
# Get ALL unresolved threads (no source filter)
gh api graphql -f query='
  query {
    repository(owner: "OWNER", name: "REPO") {
      pullRequest(number: PR_NUM) {
        reviewThreads(first: 100) {
          nodes {
            id
            isResolved
            comments(first: 1) {
              nodes {
                author { login }
                body
              }
            }
          }
        }
      }
    }
  }
' | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)]'

# If count > 0, PR is NOT ready to merge
```

## Why This Matters

1. **Branch protection rules** don't distinguish bot vs human
2. **Merge conflicts** can occur with unresolved conversations
3. **Code quality** - bots often catch real issues
4. **Trust** - dismissing comments damages process integrity

## Root Cause of Error

**Session 5 PR #918**: Assumption made without checking:
- ❌ No memory supported "bot comments non-blocking"
- ❌ No protocol documentation supported it
- ❌ No ADR supported it
- ❌ Pure fabrication from LLM inference

## Correction Process

1. User challenged assumption: "where'd you get the idea that a bot comment is NOT blocking?"
2. Searched memories: No evidence found
3. Verified comment had no reply: Posted reply
4. Documented correct principle: This memory

## Related Memories

- [pr-review-007-merge-state-verification](pr-review-007-merge-state-verification.md) - Verify merge state before review
- [pr-review-008-session-state-continuity](pr-review-008-session-state-continuity.md) - Session state for multi-round reviews
- [pr-review-acknowledgment](pr-review-acknowledgment.md) - Comment acknowledgment patterns

## Session Reference

- **Session 5** (2026-01-16): PR #918 cursor[bot] comment handling
- **Commit**: Reply 2697041329 posted to comment 2696913148
- **Learning**: Corrected false assumption, documented correct principle
