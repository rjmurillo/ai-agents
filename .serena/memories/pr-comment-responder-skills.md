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

**Statement**: Prioritize cursor[bot] review comments; 100% actionability rate

**Context**: During PR comment triage, when multiple reviewers present

**Evidence**:

- PR #52 - 1/1 cursor[bot] comment CRITICAL (untracked file detection bug)
- PR #47 - 2/2 cursor[bot] comments were actionable bugs (test pollution, PathInfo type)
- PR #32 - 2/2 cursor[bot] comments actionable
- **Total**: 5/5 actionable (100% signal quality maintained)
- Signal-to-noise: cursor 5/5 (100%) vs other bots 8/20 (40%)

**Atomicity**: 96%

**Tag**: helpful (triage prioritization)

**Validated**: 3 (PR #32, #47, #52)

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

## Reviewer Signal Quality Evaluation

### Per-Reviewer Performance (Cumulative)

| Reviewer | PRs Reviewed | Comments | Actionable | Signal Rate | Trend |
|----------|-------------|----------|------------|-------------|-------|
| **cursor[bot]** | #32, #47, #52 | 5 | 5 | **100%** | ✅ Stable |
| **Copilot** | #32, #47, #52 | 9 | 4 | **44%** | ↑ Improving |
| **coderabbitai[bot]** | #32, #47, #52 | 6 | 1 | **17%** | ↓ Low signal |

### Per-PR Breakdown

#### PR #52 (2025-12-17)

| Reviewer | Comments | Actionable | Details |
|----------|----------|------------|---------|
| cursor[bot] | 1 | 1 (100%) | CRITICAL: untracked file detection bug |
| Copilot | 2 | 2 (100%) | WhatIf+PassThru return value, missing test |
| coderabbitai[bot] | 2 | 0 (0%) | 1 duplicate of Copilot, 1 summary |

**Notes:**

- cursor[bot] maintained 100% (5/5 total)
- Copilot unusually high signal (normally ~30%)
- CodeRabbit duplicate reduced signal value

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

Based on cumulative signal quality:

| Priority | Reviewer | Action | Rationale |
|----------|----------|--------|-----------|
| **P0** | cursor[bot] | Process immediately | 100% actionable, finds CRITICAL bugs |
| **P1** | Human reviewers | Process with priority | Domain expertise, context |
| **P2** | Copilot | Review carefully | ~44% signal, improving trend |
| **P3** | coderabbitai[bot] | Skim for real issues | ~17% signal, often duplicates |

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

## Metrics (as of PR #52)

- **Triage accuracy**: 100% (5/5 in PR #52, 8/8 in PR #47)
- **cursor[bot] actionability**: 100% (5/5 across PR #32, #47, #52)
- **Copilot actionability**: 44% (4/9 across PR #32, #47, #52)
- **CodeRabbit actionability**: 17% (1/6 across PR #32, #47, #52)
- **Quick Fix efficiency**: 3 bugs in 4 minutes (PR #52)
