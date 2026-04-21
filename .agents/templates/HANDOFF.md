# Session Handoff — {ISO_TIMESTAMP}

<!--
Per-issue session handoff template. Copy to:
  .agents/sessions/handoffs/{ISO_DATE}-{ISSUE_NUMBER}-handoff.md

See: .agents/sessions/handoffs/README.md for naming, lifecycle, and scope.
See: .agents/architecture/ADR-014-distributed-handoff-architecture.md for tier model.
-->

## Status

- **Issue**: #{ISSUE_NUMBER} — {issue title}
- **Branch**: {branch name}
- **Task**: {one-sentence description of the in-flight task}
- **Phase**: {planning | implementing | testing | reviewing | blocked | complete}
- **Progress**: {percent complete or enumerated steps done vs total}

## Files Modified

<!-- List only files changed in this session. Use repo-relative paths. -->

- `path/to/file.ext` — {what changed and why}

## Decisions Made

<!-- Decisions that persist beyond this session. Include alternatives considered. -->

- **{decision}**: {rationale}
  - Alternatives considered: {list}
  - Reference: {ADR / issue / PR / memory path, if any}

## Blocked Items

<!-- Anything the next session cannot proceed on without external input. -->

- **{blocker}**: {what is needed to unblock, who owns it}

## Next Steps

<!-- Concrete, actionable. The next session picks up here without re-discovery. -->

1. {concrete next action}
2. {concrete next action}
3. {concrete next action}

## Context for Next Session

<!-- Non-obvious context the next session needs: subtle invariants, avoided paths,
     external constraints not captured elsewhere. Skip if the code and session log
     already make it obvious. -->

- {non-obvious context}

## Verification on Resume

<!-- Steps the next session runs to confirm handoff claims still hold.
     These are not optional. Stale handoffs cause silent state corruption. -->

- [ ] `git status` matches "Files Modified" (no unexpected drift)
- [ ] Branch matches: `{branch name}`
- [ ] Blocked items still blocked (no out-of-band resolution)
- [ ] Next step #1 is still the correct starting point

## Related

- Session log: `.agents/sessions/{YYYY-MM-DD-session-NN}.json`
- Previous handoff: `.agents/sessions/handoffs/{prior-file}.md` (if continuing)
- PR: {PR URL or "none yet"}
