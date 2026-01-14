# Skill Observations: reflect

**Last Updated**: 2026-01-14
**Sessions Analyzed**: 2

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

## Edge Cases (MED confidence)

These are scenarios to handle:

- DRY violations may be intentional trade-offs. Document rationale: function isolation vs coupling, change frequency, maintenance burden (Session 2026-01-14-session-01, 2026-01-14)
- Error handling strategy differs by hook type. Stop hooks: SilentlyContinue (never block session). PreCommit hooks: Stop (fail fast) (Session 2026-01-14-session-01, 2026-01-14)

## Notes for Review (LOW confidence)

These are observations that may become patterns:
