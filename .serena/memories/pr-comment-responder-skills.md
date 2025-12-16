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

### Skill-PR-004: Review Reply Endpoint

**Statement**: Use `gh api repos/OWNER/REPO/pulls/PR/comments -X POST -F in_reply_to=ID -f body=TEXT` for thread replies

**Context**: When responding to specific review comment threads (not issue-level comments)

**Evidence**:

- PR #32 - issuecomment-3651048065 and issuecomment-3651112861 lost review thread context
- PR #47 - Initial issue comment attempt failed; retry with correct review API succeeded (2/2 thread replies posted)

**Atomicity**: 96%

**Validation Count**: 2

**Tag**: helpful

---

---

### Skill-Workflow-001: Quick Fix Path

**Statement**: Bypass orchestrator for atomic bugs: single-file, single-function, clear fix

**Context**: During PR comment triage when bug meets atomic criteria

**Evidence**: PR #47 - 2 bugs (test pollution, PathInfo type) fixed via direct implementer delegation in ~10 minutes

**Atomicity**: 89%

**Tag**: helpful (routing efficiency)

---

### Skill-QA-001: QA Integration Discipline

**Statement**: Run QA agent after all implementer work, regardless of perceived fix complexity

**Context**: After implementer completes any code change

**Evidence**: PR #47 - QA added regression test for PathInfo bug (commit a15a3cf), preventing future recurrence; verified 17/17 tests passing

**Atomicity**: 95%

**Tag**: helpful (test coverage, regression prevention)

---

### Skill-PR-006: cursor[bot] Signal Quality

**Statement**: Prioritize cursor[bot] review comments; 100% actionability rate (4/4 in PR #32, #47)

**Context**: During PR comment triage, when multiple reviewers present

**Evidence**:

- PR #47 - 2/2 cursor[bot] comments were actionable bugs (test pollution, PathInfo type)
- PR #32 - 2/2 cursor[bot] comments actionable
- Signal-to-noise: cursor 4/4 (100%) vs other bots 6/14 (43%)

**Atomicity**: 96%

**Tag**: helpful (triage prioritization)

---

## Application Checklist

When handling PR review comments:

1. [ ] Enumerate ALL reviewers before triaging (Skill-PR-001)
2. [ ] Prioritize cursor[bot] comments first (Skill-PR-006)
3. [ ] Parse each comment independently, not by file (Skill-PR-002)
4. [ ] For atomic bugs, use Quick Fix path to implementer (Skill-Workflow-001)
5. [ ] Always delegate to QA after implementer (Skill-QA-001)
6. [ ] Use review reply endpoint: `gh api repos/OWNER/REPO/pulls/PR/comments -X POST -F in_reply_to=ID -f body=TEXT` (Skill-PR-004)
7. [ ] Verify count before claiming done (Skill-PR-003)

## Metrics (as of PR #47)

- **Triage accuracy**: 100% (0/8 missed in PR #47)
- **cursor[bot] actionability**: 100% (4/4 across PR #32, #47)
- **Noise ratio**: 75% (6/8 non-actionable in PR #47)
- **Quick Fix efficiency**: 2 bugs, ~10 minutes, 2 single-line fixes
