# Skill Observations: pr-review

**Last Updated**: 2026-04-13
**Sessions Analyzed**: 14

## Purpose

This memory captures learnings from PR review workflows, GitHub API patterns, and review thread management across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Thread resolution requires explicit action: Replying to a review comment does NOT auto-resolve the thread. Must use explicit GraphQL mutation `resolveReviewThread` (Session 870, Session 4, 2026-01-11, 2026-01-16)
  - Evidence: Session 870 - Posted replies to review threads, threads remained unresolved until GraphQL mutation called
  - Evidence: Session 4 PR #918 - Resolved 3 review threads via GraphQL after posting replies
- GitHub API limitation: Reactions to code-scanning alerts fail with HTTP 422 "Reactions are not available for code scanning alerts" - no workaround available (Session 870, 2026-01-11)
- Bot comments can reference stale commits - verify current branch state before accepting bot claims as accurate. Bot may reference old commit when files have moved/changed (Sessions 4, 7, PR #918, PR #908, 2026-01-16)
  - Evidence: cursor[bot] referenced commit e53617c1 claiming test file paths incorrect, but paths were correct at current commit 7dd59c45. Multiple instances of bot comments referencing outdated commit state
- Bot false positives on file deletion - verify file exists on both branches before accepting deletion claim. Use `git show branch:path` to confirm (Session 822, PR #859, 2026-01-11)
  - Evidence: gemini-code-assist[bot] claimed .PSScriptAnalyzerSettings.psd1 was being deleted, but file existed unchanged on both main and feature branch
- ALL PR comments (bot or human) are blocking and must be resolved - no exceptions. Bot comments have equal weight to human reviewer comments (Session 5, PR #918, 2026-01-16)
  - Evidence: User correction - "User correctly identified that ALL comments (bot or human) are blocking and must be resolved. My assumption that 'bot comments are non-blocking' had no basis in documented knowledge."
  - Memory created: pr-review-015-all-comments-blocking.md
- Batch response pattern for PR comments - single comprehensive commit addressing all comments cleaner than N individual commits (Session 4, PR #918, 2026-01-16)
  - Evidence: Batch 37 - Responded to all 11 bot review comments with fixes in one commit
- 24-commit limit is a blocker for PR merge - exceeding commit count limit prevents merge regardless of content quality (Session 4, PR #918, 2026-01-16)
  - Evidence: Batch 37 - PR #918 had 24 commits, user noted commit limit blocker requiring squash or label
- Bot false positives require code verification before implementing - verify current code state before accepting bot claims (Session 4, PR #918, 2026-01-16)
  - Evidence: Batch 37 - Bot claimed paths incorrect but verification showed paths were correct at current commit
- **Outdated threads still block merge.** `isOutdated: true` on a review thread does NOT mean it counts as resolved for the `required_review_thread_resolution` ruleset. Filtering thread sweeps with `not isResolved and not isOutdated` is incorrect; use `not isResolved` alone. After every push that moves lines, explicitly resolve any thread that isn't already marked `isResolved: true`. (Session 2026-04-13, PR #1633)
  - Evidence: 9 copilot-pull-request-reviewer threads flipped from unresolved to outdated (not resolved) after edits moved line references. My initial resolve sweep filtered them out. Merge stayed BLOCKED until I swept all non-resolved threads and explicitly called `resolveReviewThread` on each.
- **Bot reviewers catch up on historical commits after push.** When a branch has multiple rapid commits, coderabbit and copilot-pull-request-reviewer will submit reviews against EARLIER commits (not HEAD), sometimes minutes or hours after the fact. Review findings may reference content already fixed in a later commit. Map the review's `commit_id` against current HEAD via `git log` before triaging — findings on stale commits are often already addressed. (Session 2026-04-13, PR #1633)
  - Evidence: Review `4096668426` was submitted against commit `2ab9b6ab` (6 commits behind HEAD at time of review). Its 4 findings were all already addressed in `ee9f5f23` + `8d464f62`. Saved hours by checking commit IDs first.

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Parallel review agents catch different issue types - comment-analyzer finds factual errors, code-reviewer finds architectural conflicts (Session 02, PR #871, 2026-01-11)
  - Evidence: Launched 3 parallel agents (comment-analyzer, code-reviewer, code-simplifier). comment-analyzer found 2 critical factual inaccuracies (Python claim contradicts ADR-005, Forgetful tool name incorrect), code-reviewer found document purpose drift (.gemini/styleguide.md grew from routing-index to comprehensive reference)
- Incoherence detection skill finds 10+ documentation inconsistencies across 6 dimensions - systematic pattern for identifying doc drift (Session 02, PR #871, 2026-01-11)
  - Evidence: Incoherence analysis identified 10 issues across 6 dimensions (A-K): ADR reference mismatches, terminology inconsistencies, examples contradicting constraints, etc. Created comprehensive report and GitHub issue #881 for tracking
- Commit limit bypass requires explicit label addition via gh CLI - not automatic (Session 812, 2026-01-09)
  - Evidence: PR #853 had 26 commits (limit 20). Added commit-limit-bypass label via `gh issue edit 853 --add-label commit-limit-bypass`
- Bot review comments require individual acknowledgment with fix details - document what was changed and why (Session 03, 2026-01-16)
  - Evidence: Batch 36 - Acknowledged each bot comment with specific fix details for clarity
- Shell script code duplication should be consolidated using parameter expansion for maintainability (Session 03, 2026-01-16)
  - Evidence: Batch 36 - Consolidated duplicate shell script code using parameter expansion pattern
- Memory first before multi-step reasoning - retrieve context from memory systems before planning (Session 4, 2026-01-16)
  - Evidence: Batch 37 - Memory retrieval pattern before engaging in multi-step PR review reasoning
- Eyes reaction as acknowledgment pattern - use 👀 to acknowledge review comments received (Session 4, 2026-01-16)
  - Evidence: Batch 37 - Used eyes reaction to acknowledge all review comments before batch processing

## Edge Cases (MED confidence)

These are scenarios to handle:

- GraphQL pagination with `first: 100` captures old threads but misses newest - need to query both `first: N` and `last: N` for comprehensive coverage when dealing with large review thread counts (Session 7, PR #908, 2026-01-16)
  - Evidence: Query with first: 100 returned old resolved threads but didn't include most recent unresolved threads at end of list
- **Markdown doc validators (Path Normalization, etc.) match literals inside code spans without parsing markdown.** When a plan doc quotes a regex pattern that happens to contain the validator's own trigger strings (for example, Linux home-dir prefixes or macOS user-dir prefixes inside a pattern span), the validator fires on the documentation itself. Fix: describe the pattern in prose and put the actual regex in the implementation file. (Session 2026-04-13, PR #1633)
  - Evidence: REQ-2.3 in the stage-1 plan contained a literal regex in a markdown code span that matched Linux home-dir prefixes, macOS user-dir prefixes, and Windows drive-letter prefixes. CI job `Validate Path Normalization` reported it as 2 absolute-path violations (macOS User Path + Linux Home Path) on line 81 of the plan file.
- **Docs-only diffs should skip the specialist army.** A pure-markdown PR (plan file, README, changelog) has no code surface for testing/security/performance/maintainability specialists to analyze. Group to "no code, docs-only diff — skipping specialists" immediately in /review's scope detection, not after the fact. (Session 2026-04-13, PR #1633)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-11 | Session 870 | HIGH | Thread resolution requires explicit GraphQL mutation, not just reply |
| 2026-01-16 | Session 4, PR #918 | HIGH | Thread resolution reinforced (3 threads resolved via GraphQL) |
| 2026-01-11 | Session 870 | HIGH | GitHub API reactions fail for code-scanning alerts (HTTP 422) |
| 2026-01-16 | Sessions 4, 7, PR #918, PR #908 | HIGH | Bot comments can reference stale commits |
| 2026-01-11 | Session 822, PR #859 | HIGH | Bot false positives on file deletion |
| 2026-01-16 | Session 5, PR #918 | HIGH | ALL PR comments (bot or human) are blocking - user correction |
| 2026-01-16 | Session 4, PR #918 | HIGH | Batch response pattern for PR comments |
| 2026-01-16 | Session 4, PR #918 | HIGH | 24-commit limit blocker for merge |
| 2026-01-16 | Session 4, PR #918 | HIGH | Bot false positives require code verification |
| 2026-01-16 | Session 7, PR #908 | MED | GraphQL pagination with first: N misses newest items |
| 2026-01-11 | Session 02, PR #871 | MED | Parallel review agents catch different issue types |
| 2026-01-11 | Session 02, PR #871 | MED | Incoherence detection finds 10+ inconsistencies |
| 2026-01-09 | Session 812 | MED | Commit limit bypass label requirement |
| 2026-01-16 | Session 03 | MED | Bot review comments require individual acknowledgment |
| 2026-01-16 | Session 03 | MED | Shell script code duplication consolidation pattern |
| 2026-01-16 | Session 4 | MED | Memory first before multi-step reasoning |
| 2026-01-16 | Session 4 | MED | Eyes reaction as acknowledgment pattern |
| 2026-04-13 | PR #1633 | HIGH | Outdated threads still block merge — resolve explicitly after every push |
| 2026-04-13 | PR #1633 | HIGH | Bot reviewers catch up on historical commits; map review commit_id vs HEAD before triaging |
| 2026-04-13 | PR #1633 | MED | Markdown doc validators match literals inside code spans; describe regex patterns in prose |
| 2026-04-13 | PR #1633 | MED | Docs-only diffs should skip specialist army in /review |

## Related

- [github-observations](github-observations.md)
- [pr-comment-responder](../pr-comment-responder/)
