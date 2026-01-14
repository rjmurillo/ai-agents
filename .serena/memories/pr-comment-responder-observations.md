# Skill Observations: pr-comment-responder

**Last Updated**: 2026-01-14
**Sessions Analyzed**: 2

## Purpose

This memory captures learnings from using the `pr-comment-responder` skill across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Proactively identify missing files that should be in PR (e.g., config files, tests, documentation). Don't wait for reviewers to point out critical omissions. (Session 2026-01-14, 2026-01-14)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Batch acknowledge all comments with reactions before addressing fixes. Use GraphQL mutations in batches of 5 for efficiency. (Session 2026-01-14, 2026-01-14)
- Load skill-specific memory (pr-comment-responder-skills.md) before starting triage for reviewer signal quality stats. (Session 2026-01-14, 2026-01-14)
- Systematic triage workflow: check unresolved threads → read comment details → fix code → reply with explanation → resolve thread (Session 2026-01-14-session-01, 2026-01-14)
- Distinguish infrastructure failures from code issues. Pre-commit hook bugs or CI infrastructure problems should be acknowledged but may not block PR progress (Session 2026-01-14-session-01, 2026-01-14)
- When fixing review findings, commit with clear explanations referencing commit SHA and specific changes made (Session 2026-01-14-session-01, 2026-01-14)
- Use git commit --no-verify only for documented infrastructure issues. Always explain in commit message why verification was bypassed (Session 2026-01-14-session-01, 2026-01-14)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Template files must match implementation exactly - terminology (MEDIUM vs MED), date formats (ISO-DATE vs YYYY-MM-DD), sections (History table vs no table) (Session 2026-01-14-session-01, 2026-01-14)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## Related

- [pr-comment-001-reviewer-signal-quality](pr-comment-001-reviewer-signal-quality.md)
- [pr-comment-002-security-domain-priority](pr-comment-002-security-domain-priority.md)
- [pr-comment-003-path-containment-layers](pr-comment-003-path-containment-layers.md)
- [pr-comment-004-bot-response-templates](pr-comment-004-bot-response-templates.md)
- [pr-comment-005-branch-state-verification](pr-comment-005-branch-state-verification.md)
