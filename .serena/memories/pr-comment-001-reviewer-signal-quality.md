# Skill: Reviewer Signal Quality Tracking

## Statement

Track per-reviewer actionability rates to prioritize high-signal reviewers during PR comment triage.

## Trigger

When processing PR review comments from multiple reviewers.

## Action

1. Maintain cumulative stats per reviewer (PRs, comments, actionable count, signal rate)
2. Process comments from high-signal reviewers first
3. Update stats after each PR session

## Benefit

Reduces wasted effort on false positives from low-signal reviewers.

## Reference Data

Current signal rates (2025-12-29):

| Reviewer | Signal |
|----------|--------|
| cursor[bot] | 100% |
| gemini-code-assist[bot] | 100% |
| Copilot | 100% |
| rjmurillo (owner) | 100% |
| coderabbitai[bot] | 50% |

## Evidence

- PR #505, #484, #488, #490: Tracked 9 comments across 4 PRs
- cursor[bot]: 28/28 actionable (Session 60-65)
- coderabbitai[bot]: 3/6 actionable (false positives in documentation domain)

## Atomicity

**Score**: 94%

**Justification**: Single concept (signal quality tracking). Minor compound with "prioritize" action but inseparable from tracking purpose.

## Category

pr-comment-responder

## Created

2025-12-29

## Related

- [pr-comment-002-security-domain-priority](pr-comment-002-security-domain-priority.md)
- [pr-comment-003-path-containment-layers](pr-comment-003-path-containment-layers.md)
- [pr-comment-004-bot-response-templates](pr-comment-004-bot-response-templates.md)
- [pr-comment-005-branch-state-verification](pr-comment-005-branch-state-verification.md)
- [pr-comment-index](pr-comment-index.md)
