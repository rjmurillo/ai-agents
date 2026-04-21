# Failure Pattern: False Completion Markers

**Last Updated**: 2026-04-21
**Status**: active
**Severity**: High

## Summary

Agents report tasks as "done" while artifacts remain incomplete: tests missing, coverage not reached, acceptance criteria partially satisfied, or commits not pushed. The gap between declared completion and observable completion corrupts downstream planning.

## What Failed

- `2026-01-13-pr894-test-coverage-failure.md`: Agent declared coverage complete while untested branches remained.
- Orchestrator stop criterion "completely solved" was too vague to evaluate (tracked in Issue #1667).

## What Worked

- Verifiable stop criteria: numeric coverage threshold, explicit acceptance checklist, output-of-tool evidence attached to the session log.
- Session-end skill auto-populates evidence fields (commit SHA, lint results, memory updates) and refuses to close a session with missing MUST items.

## Current Recommendation

Define completion as "an artifact a tool can inspect". Replace "done" with:

- A commit SHA.
- A passing test count.
- A linter exit code.
- A file whose existence is checked by a hook.

If a criterion cannot be reduced to an inspectable artifact, rewrite it until it can.

## References

- `.agents/governance/FAILURE-MODES.md` Section 4
- Issue #1667 (orchestrator stop criterion)
- `.claude/skills/session-end/`
- Retrospective: `.agents/retrospective/2026-01-13-pr894-test-coverage-failure.md`
