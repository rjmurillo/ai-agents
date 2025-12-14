# PR Comment Responder Skills

## Discovered: 2025-12-14 from PR #32 Retrospective

### Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate all reviewers (gh pr view --json reviews) before triaging to avoid single-bot blindness

**Context**: When handling PR review comments with multiple bots (Copilot, CodeRabbit)

**Evidence**: PR #32 - Agent counted only Copilot (5 comments) when CodeRabbit also reviewed (2 comments)

**Atomicity**: 92%

**Tag**: helpful when applied, harmful when skipped

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

**Evidence**: PR #32 - Agent claimed "All 5 comments" when 7 total existed

**Atomicity**: 94%

**Tag**: harmful when skipped (premature completion claim)

---

### Skill-PR-004: Review Reply Endpoint

**Statement**: Use `gh api pulls/comments/{id}/replies` for thread-preserving responses instead of issue comments

**Context**: When responding to specific review comments

**Evidence**: PR #32 - issuecomment-3651048065 and issuecomment-3651112861 lost review thread context

**Atomicity**: 90%

**Tag**: harmful when using issue comments (context loss)

---

## Application Checklist

When handling PR review comments:

1. [ ] Enumerate ALL reviewers before triaging
2. [ ] Parse each comment independently (not by file)
3. [ ] Use review reply endpoint for thread context
4. [ ] Verify count before claiming done
