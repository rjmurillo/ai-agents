# PR Review: Bot Reviewer Triage

## Skill-PR-006: Reviewer Signal Quality

**Statement**: Prioritize reviewers by historical actionability rate.

**Atomicity**: 96% | **Validated**: 14 PRs

| Priority | Reviewer | Signal Rate | Action |
|----------|----------|-------------|--------|
| **P0** | cursor[bot] | **100%** (28/28) | Process immediately |
| **P1** | Human reviewers | N/A | Domain expertise |
| **P2** | Copilot | **90%** (17/19) | Review with priority |
| **P2** | coderabbitai[bot] | ~50% (163 comments) | Review carefully |
| **P3** | gemini-code-assist[bot] | **0%** (0/5 on PR 308) | Check exclusion context |

**Comment Type Actionability**:

| Type | Rate | Examples |
|------|------|----------|
| Bug reports | ~90% | cursor[bot] bugs, type errors |
| Missing coverage | ~70% | Test gaps, edge cases |
| Style suggestions | ~20% | Formatting, naming |
| Summaries | 0% | CodeRabbit walkthroughs |

## Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate ALL reviewers before triaging to avoid single-bot blindness.

```bash
gh pr view PR --json reviews --jq '.reviews[].author.login' | sort -u
```

## Skill-PR-002: Independent Comment Parsing

**Statement**: Parse each comment independently; same-file comments may address different issues.

## Skill-PR-003: Verification Count

**Statement**: Verify addressed_count matches total_comment_count before claiming completion.

## Related

- [pr-review-001-reviewer-enumeration](pr-review-001-reviewer-enumeration.md)
- [pr-review-002-independent-comment-parsing](pr-review-002-independent-comment-parsing.md)
- [pr-review-003-verification-count](pr-review-003-verification-count.md)
- [pr-review-006-reviewer-signal-quality](pr-review-006-reviewer-signal-quality.md)
- [pr-review-007-ci-verification](pr-review-007-ci-verification.md)
