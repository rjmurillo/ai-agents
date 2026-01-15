# Skill Observations: code-review

**Last Updated**: 2026-01-14
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Filter issues by confidence threshold >= 80. Issues scoring 75 are real but not critical enough to block PR approval. The scoring rubric defines 75 as "Highly confident" but the threshold ensures only verified critical issues are reported. (observed 2026-01-14; external review session not logged in .agents/sessions/)
- Always run 5 parallel review agents with Sonnet model, not Haiku. Use Haiku only for eligibility checks and issue scoring. Skill instructions specify "launch 5 parallel Sonnet agents" at step 4. Use the project Claude router skill (`claude-router:standard-executor`) with model=sonnet. (observed 2026-01-14; external review session not logged in .agents/sessions/)

## Preferences (MED confidence)

- Use parallel task launches for all 5 review agents in a single message, not sequential. Maximizes efficiency and reduces total review time. Successfully launched 5 parallel agents with one Task tool invocation block, completing all reviews simultaneously. (observed 2026-01-14; external review session not logged in .agents/sessions/)
- Always include GitHub permalink with full SHA in issue reports. Use format: `https://github.com/{owner}/{repo}/blob/{full-sha}/{file}#L{start}-L{end}`. Retrieve SHA with `gh pr view --json headRefOid` and construct proper permalinks with line ranges including context lines. (observed 2026-01-14; external review session not logged in .agents/sessions/)

## Edge Cases (MED confidence)

- When scoring issues, verify the actual code at the referenced lines. False positives from initial scans can be caught during scoring phase. Example: naming convention issue was initially flagged but scored 0 during verification because actual code inspection showed no issue existed. (observed 2026-01-14; external review session not logged in .agents/sessions/)
- Check if PR is still eligible before posting final comment. PR state can change during multi-step review process. Verify PR state hasn't changed (still OPEN, not draft) before posting final comment per step 7 of skill instructions. (observed 2026-01-14; external review session not logged in .agents/sessions/)

## Notes for Review (LOW confidence)

- (none yet)
