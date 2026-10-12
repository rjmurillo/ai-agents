# Session Handoff: {ISO_TIMESTAMP}

<!--
Per-issue session handoff template. Copy to:
  .project-toolkit/sessions/handoffs/{ISO_DATE}-{ISSUE_NUMBER}-handoff.md

See: .project-toolkit/sessions/handoffs/README.md for naming, lifecycle, and scope.
See: .project-toolkit/architecture/ADR-014-distributed-handoff-architecture.md for tier model.
-->

## Status

- **Issue**: #{ISSUE_NUMBER}, {issue title}
- **Task**: {one-sentence description of the in-flight task}
- **Progress**: {percent complete or enumerated steps done vs total}

## State Record

<!-- The resume check reads this block. Keep one `- **Key**: value` line per field.
     Remote, Branch, Worktree, Head SHA, and Timestamp are the live-state anchors.
     Verify them with: uv run python scripts/validation/check_handoff_resume.py <this file>
     An empty field or a {placeholder} counts as missing and the resume check holds. -->

- **Remote**: {owner/name}
- **Branch**: {branch name}
- **Worktree**: {absolute worktree path}
- **Head SHA**: {git rev-parse HEAD at handoff time}
- **Timestamp**: {ISO 8601 UTC, for example 2026-09-30T14:02Z}
- **Objective**: {what the work must achieve}
- **Non-goals**: {what the work must not do}
- **Risk tier**: {read-only | shared-repository | consequential}
- **Acceptance**: {observable criteria that close the work}
- **Phase**: {planning | implementing | testing | reviewing | blocked | complete}
- **Next action**: {the one exact next step}
- **Validation run**: {commands actually run and their results, or "none"}
- **Residual risks**: {unresolved risks, or "none known"}
- **Escalation owner**: {who decides when the record and the repository disagree}

## Files Modified

<!-- List only files changed in this session. Use repo-relative paths. -->

- `path/to/file.ext`: {what changed and why}

## Decisions Made

<!-- Decisions that persist beyond this session. Include alternatives considered.
     Every decision needs a Provenance line. Mark a replaced decision with a
     Superseded by line instead of deleting it. -->

- **{decision}**: {rationale}
  - Alternatives considered: {list}
  - Provenance: {who or what decided it: ADR / issue comment / PR / agent finding / memory path}
  - Superseded by: {later decision, only when replaced}

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

Run the checker first. It compares Remote, Branch, Worktree, and Head SHA with the
live repository and fails closed. Exit 0 means the anchors match. Exit 1 means HOLD:
surface the contradiction and do not mutate.

- [ ] `uv run python scripts/validation/check_handoff_resume.py <this file>` exits 0
- [ ] `git status` matches "Files Modified" (a change caused by the next action is not drift)
- [ ] Next action is not already done, reverted, or superseded in `git log` since Head SHA
- [ ] Blocked items still blocked (no out-of-band resolution)
- [ ] Acceptance and Risk tier restored from the State Record before acting
- [ ] Decisions carry Provenance; superseded ones are marked
- [ ] A completion summary is not evidence of completion: confirm with the validation run

## Related

- Session log: `.project-toolkit/sessions/{YYYY-MM-DD-session-NN}.json`
- Previous handoff: `.project-toolkit/sessions/handoffs/{prior-file}.md` (if continuing)
- PR: {PR URL or "none yet"}
