---
applyTo: '**'
---

# Session Log Mechanics

`.agents/SESSION-PROTOCOL.md` describes what a session log contains. This rule
covers two enforcement mechanics that the protocol document does not state and
that both fail loudly at commit time.

Scoped to `.agents/**` rather than `**` on purpose. Both rules fire only when a
change touches that tree, and the always-on instruction ceiling
(`scripts/validation/instruction_budget.py`) has under 500 bytes of headroom, so
a universally scoped copy would block the next contributor's rule. Note that the
generator currently ships this rule to the plugin with `applyTo: '**'`, because
`.agents/**` is filtered as internal-only and the empty scope is backfilled as
universal; that is issue #4317, not a property of this rule.

## MUST

1. **The log lands in the same commit as the change.** A commit that stages
   anything under `.agents/**` MUST carry a session log named
   `.agents/sessions/YYYY-MM-DD-session-NN<slug>.json` in that same commit.
   `scripts/validation/git_hook_policy.py session` rejects the commit with
   `ERROR: staged .agents changes require a JSON session log` otherwise. It runs
   on every `.agents/**` path, not only on work long enough to feel like a
   session. Writing the log afterwards does not clear the rejection; the log and
   the change must land together. One exception: a merge in progress skips the
   check, both at the hook (`lefthook.yml`, `skip: [merge]`) and in the checker
   (`check_sessions` returns 0 when `_merge_in_progress`).

2. **Record `endingCommit` in a follow-up commit, never by amending.** Amending
   replaces the commit whose SHA the log names, so `validate_session_json.py`
   then reports the recorded SHA as unreachable (issue #3618). Commit the work
   with `endingCommit` empty, which is only a warning, then commit the SHA in a
   second commit. The reachability check returns no finding in a shallow clone
   (`session_scope.py` short-circuits when `--is-shallow-repository` is true), so
   a green CI run on a shallow checkout is not evidence the SHA is reachable.

3. **Re-point `endingCommit` after any rebase of a branch that carries a session
   log.** Rebasing rewrites every commit on the branch, so it orphans a recorded
   SHA exactly the way amending does, and the validator reports the same
   unreachable-SHA error. The difference that makes this the more likely trap:
   you amend on purpose and know the log is in play, but you rebase for an
   unrelated reason (picking up a new base to unblock a push), so nothing
   prompts you to think about the log at all. The failure then surfaces on the
   PR, not locally. After rebasing, set `endingCommit` to the post-rebase `HEAD`
   and commit that edit; `HEAD` becomes an ancestor of the new commit, so the
   reachability check passes.

## References

- `.agents/SESSION-PROTOCOL.md`. What a session log contains.
- `scripts/validation/git_hook_policy.py`. The `session` subcommand that blocks
  the commit.
- `scripts/validate_session_json.py`. The reachability check on `endingCommit`.
- Issue #3618. The amend-breaks-endingCommit report.
