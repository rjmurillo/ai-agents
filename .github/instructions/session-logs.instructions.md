---
applyTo: .agents/**
---

# Session Log Mechanics

`.agents/SESSION-PROTOCOL.md` describes what a session log contains. This rule
covers two enforcement mechanics that the protocol document does not state and
that both fail loudly at commit time.

Scoped to `.agents/**` rather than `**` on purpose. Both rules fire only when a
change touches that tree, and the always-on instruction ceiling
(`scripts/validation/instruction_budget.py`) has under 500 bytes of headroom, so
a universally scoped copy would block the next contributor's rule.

## MUST

1. **The log lands in the same commit as the change.** A commit that stages
   anything under `.agents/**` MUST carry a session log named
   `.agents/sessions/YYYY-MM-DD-session-NN<slug>.json` in that same commit.
   `scripts/validation/git_hook_policy.py session` rejects the commit with
   `ERROR: staged .agents changes require a JSON session log` otherwise. It runs
   on every `.agents/**` path, not only on work long enough to feel like a
   session. Writing the log afterwards does not clear the rejection; the log and
   the change must land together.

2. **Record `endingCommit` in a follow-up commit, never by amending.** Amending
   replaces the commit whose SHA the log names, so `validate_session_json.py`
   then reports the recorded SHA as unreachable (issue #3618). Commit the work
   with `endingCommit` empty, which is only a warning, then commit the SHA in a
   second commit.

## References

- `.agents/SESSION-PROTOCOL.md`. What a session log contains.
- `scripts/validation/git_hook_policy.py`. The `session` subcommand that blocks
  the commit.
- `scripts/validate_session_json.py`. The reachability check on `endingCommit`.
- Issue #3618. The amend-breaks-endingCommit report.
