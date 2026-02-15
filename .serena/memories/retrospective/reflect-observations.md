# Skill Observations: reflect

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 3

## Purpose

This memory captures learnings from using the `reflect` skill across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Use urgent, action-oriented language in descriptions: "CRITICAL", "LOST forever", "Invoke EARLY and OFTEN" (Session 2026-01-13-session-906, 2026-01-13)
- Include proactive trigger examples in skill frontmatter description (Session 2026-01-13-session-906, 2026-01-13)
- Add priority indicators (🔴🟡🟢) to make trigger urgency visible (Session 2026-01-13-session-906, 2026-01-13)
- Document architecture decision rationale when deviating from architect recommendations. Reference ADR compliance and trade-offs made (Session 2026-01-14-session-01, 2026-01-14)
- Template placeholders should be unambiguous. Use specific format examples ({YYYY-MM-DD}) not generic labels ({ISO-DATE}) (Session 2026-01-14-session-01, 2026-01-14)
- Bootstrap workflows - Extract learnings from large datasets (issues, PRs, documentation) by using reflect iteratively during analysis rather than waiting for end (Session 2026-01-16-session-07, 2026-01-16)
- Reflect can be invoked mid-session for incremental learning capture, not just at session end. Useful for long-running analysis tasks where learnings emerge gradually (Session 2026-01-16-session-07, 2026-01-16)
- Stop hook captures patterns, but manual reflection during work is MORE ACCURATE because it has full conversation context and can make strategic decisions (e.g., sampling strategy) (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- DRY violations may be intentional trade-offs. Document rationale: function isolation vs coupling, change frequency, maintenance burden (Session 2026-01-14-session-01, 2026-01-14)
- Error handling strategy differs by hook type. Stop hooks: SilentlyContinue (never block session). PreCommit hooks: Stop (fail fast) (Session 2026-01-14-session-01, 2026-01-14)
- When processing large datasets (100+ items), use strategic sampling rather than exhaustive analysis. Focus on: recent items, merged PRs, issues with 'retrospective' or 'learning' labels, high-comment threads (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- Skill memories follow sidecar pattern ({skill-name}-observations.md) per ADR-007. Confirmed in PR #908 implementation (Session 2026-01-16-session-07, 2026-01-16)