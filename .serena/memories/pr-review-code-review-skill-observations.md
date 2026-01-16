# Skill Observations: code-review

**Last Updated**: 2026-01-15
**Sessions Analyzed**: 1

> **Note**: These observations describe behavior of an external Claude Code code-review skill and the external router skill `claude-router:standard-executor`. Neither of these skills is defined in this repository's `.claude/skills` directory; they are configured in the hosted review environment, not as in-repo skills.

## Constraints (HIGH confidence)

- Filter issues by confidence threshold >= 80. Issues scoring 75 are real but not critical enough to block PR approval. The scoring rubric defines 75 as "Highly confident" but the threshold ensures only verified critical issues are reported. (observed 2026-01-15; external review session, documented context in session 906)
- Always run 5 parallel review agents with Sonnet model, not Haiku. Use Haiku only for eligibility checks and issue scoring. Skill instructions specify "launch 5 parallel Sonnet agents" at step 4. Use the external Claude router skill (`claude-router:standard-executor`, configured in the hosted environment and not present in this repo's `.claude/skills` directory) with model=sonnet. (observed 2026-01-15; external review session, documented context in session 906)

## Preferences (MED confidence)

- Use parallel task launches for all 5 review agents in a single message, not sequential. Maximizes efficiency and reduces total review time. Successfully launched 5 parallel agents with one Task tool invocation block, completing all reviews simultaneously. (observed 2026-01-15; external review session, documented context in session 906)
- Always include GitHub permalink with full SHA in issue reports. Use format: `https://github.com/{owner}/{repo}/blob/{full-sha}/{file}#L{start}-L{end}`. Retrieve SHA with `gh pr view --json headRefOid` and construct proper permalinks with line ranges including context lines. (observed 2026-01-15; external review session, documented context in session 906)

## Edge Cases (MED confidence)

- When scoring issues, verify the actual code at the referenced lines. False positives from initial scans can be caught during scoring phase. Example: naming convention issue was initially flagged but scored 0 during verification because actual code inspection showed no issue existed. (observed 2026-01-15; external review session, documented context in session 906)
- Check if PR is still eligible before posting final comment. PR state can change during multi-step review process. Verify PR state hasn't changed (still OPEN, not draft) before posting final comment per step 7 of skill instructions. (observed 2026-01-15; external review session, documented context in session 906)

## Notes for Review (LOW confidence)

- (none yet)

## Related

- [pr-review-001-reviewer-enumeration](pr-review-001-reviewer-enumeration.md)
- [pr-review-002-independent-comment-parsing](pr-review-002-independent-comment-parsing.md)
- [pr-review-003-verification-count](pr-review-003-verification-count.md)
- [pr-review-006-reviewer-signal-quality](pr-review-006-reviewer-signal-quality.md)
- [pr-review-007-ci-verification](pr-review-007-ci-verification.md)
