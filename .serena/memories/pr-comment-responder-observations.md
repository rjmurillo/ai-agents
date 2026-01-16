# Skill Observations: pr-comment-responder

**Last Updated**: 2026-01-15
**Sessions Analyzed**: 4

## Purpose

This memory captures learnings from using the `pr-comment-responder` skill across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Proactively identify missing files that should be in PR (e.g., config files, tests, documentation). Don't wait for reviewers to point out critical omissions. (Session 2026-01-14, 2026-01-14)
- PRs exceeding 20 commits trigger governance violation - squash early in review process, not at merge time. (Session PR-908-reflection, 2026-01-15)
- Address security bot findings (CodeQL, etc.) before pushing subsequent updates to prevent thread accumulation. (Session PR-908-reflection, 2026-01-15)
- PRs >20 files or >500 lines require explicit scope justification and splitting plan. (Session PR-908-reflection, 2026-01-15)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Batch acknowledge all comments with reactions before addressing fixes. Use GraphQL mutations in batches of 5 for efficiency. (Session 2026-01-14, 2026-01-14)
- Load skill-specific memory (pr-comment-responder-skills.md) before starting triage for reviewer signal quality stats. (Session 2026-01-14, 2026-01-14)
- Systematic triage workflow: check unresolved threads → read comment details → fix code → reply with explanation → resolve thread (Session 2026-01-14-session-01, 2026-01-14)
- Distinguish infrastructure failures from code issues. Pre-commit hook bugs or CI infrastructure problems should be acknowledged but may not block PR progress (Session 2026-01-14-session-01, 2026-01-14)
- When fixing review findings, commit with clear explanations referencing commit SHA and specific changes made (Session 2026-01-14-session-01, 2026-01-14)
- Use git commit --no-verify only for documented infrastructure issues. Always explain in commit message why verification was bypassed (Session 2026-01-14-session-01, 2026-01-14)
- Verify fixes applied before manual thread resolution - check unaddressed comments list to confirm replies were posted (Session 2026-01-14-session-907, 2026-01-15)
- Update handoff memory proactively with session progress, metrics, and comprehensive status before session end (Session 2026-01-14-session-907, 2026-01-15)
- Large PRs (>50 files, >2000 lines) should use draft status to disable some bot reviewers until human review ready. (Session PR-908-reflection, 2026-01-15)
- Continue systematic 'Fixed in commit X' response pattern for tracking. (Session PR-908-reflection, 2026-01-15)
- Bot reviewer diversity is valuable - different bots catch different issue classes (Copilot: linting, Cursor: edge cases, CodeQL: security). (Session PR-908-reflection, 2026-01-15)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Template files must match implementation exactly - terminology (MEDIUM vs MED), date formats (ISO-DATE vs YYYY-MM-DD), sections (History table vs no table) (Session 2026-01-14-session-01, 2026-01-14)
- GitHub review threads require manual GraphQL resolution even after code fixes applied and comment replies posted (Session 2026-01-14-session-907, 2026-01-15)
- PR commit count limits can become hard blockers (e.g., 24 > 20 per issue #362) - check early and plan squashing strategy (Session 2026-01-14-session-907, 2026-01-15)
- Bot comment volume >100 is not a crisis if 70%+ are automated. Triage by reviewer type first. (Session PR-908-reflection, 2026-01-15)
- Thread resolution rate of 64% (87/136) indicates traction. <50% suggests PR scope too large or needs split. (Session PR-908-reflection, 2026-01-15)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- Parallel implementations (PowerShell + Python) create 2× review surface. Consider single implementation unless migration. (Session PR-908-reflection, 2026-01-15)
- Consider metrics: comments per file, resolution rate %, bot vs human ratio for PR health assessment. (Session PR-908-reflection, 2026-01-15)
- Naming inconsistencies (MEDIUM vs MED) across templates and code create review noise - validate consistency in templates before implementation. (Session PR-908-reflection, 2026-01-15)

## Related

- [pr-comment-001-reviewer-signal-quality](pr-comment-001-reviewer-signal-quality.md)
- [pr-comment-002-security-domain-priority](pr-comment-002-security-domain-priority.md)
- [pr-comment-003-path-containment-layers](pr-comment-003-path-containment-layers.md)
- [pr-comment-004-bot-response-templates](pr-comment-004-bot-response-templates.md)
- [pr-comment-005-branch-state-verification](pr-comment-005-branch-state-verification.md)
