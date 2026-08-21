---
paths:
  - ".agents/**"
---

# Session Log Mechanics

`.agents/schemas/session-log.schema.json` describes what a session log
contains. **Session log creation is discontinued: do not create a new
`.agents/sessions/*.json` file.** Nothing ever required one to commit, push, or
open a PR. The existing logs under `.agents/sessions/` stay in the repository
as history and remain readable by the `retrospective` skill, memory
extraction, and the PreCompact hook. This rule covers the mechanics that still
apply to a log that already exists on your branch (carried over from before
this change, or cherry-picked from an older one).

Scoped to `.agents/**` rather than `**` on purpose. The mechanics matter only
when a change touches that tree, and the always-on instruction ceiling
(`scripts/validation/instruction_budget.py`) has under 500 bytes of headroom, so
a universally scoped copy would block the next contributor's rule. Note that the
generator currently ships this rule to the plugin with `applyTo: '**'`, because
`.agents/**` is filtered as internal-only and the empty scope is backfilled as
universal; that is issue #4317, not a property of this rule.

## MUST

1. **Do not create a new session log.** Session log creation is discontinued;
   no start, end, commit, push, or PR gate ever required one, and none does
   now. If a log named `.agents/sessions/YYYY-MM-DD-session-NN<slug>.json`
   ends up staged anyway (for example, cherry-picked from an older branch),
   the `session-policy` pre-commit hook still validates it
   (`scripts/validation/git_hook_policy.py session`, a validate-if-present gate):
   a malformed log still blocks that commit. When no log is staged, the gate
   returns 0 (`check_sessions` passes when there are no session paths, and also
   when `_merge_in_progress`).

2. **Record `endingCommit` in a follow-up commit, never by amending.** Amending
   replaces the commit whose SHA the log names, so `validate_session_json.py`
   then reports the recorded SHA as unreachable (issue #3618). Commit the work
   with `endingCommit` empty, then commit the SHA in a second commit. The
   reachability check returns no finding in a shallow clone
   (`session_scope.py` short-circuits when `--is-shallow-repository` is true), so
   a green CI run on a shallow checkout is not evidence the SHA is reachable.

   **Do not leave `endingCommit` empty past that second commit.** The session
   validator only warns, but the episode extractor derives `metrics.commits`
   from the SHAs it can find: `json_metrics` calls `_collect_shas`, which reads
   `endingCommit` first, then `changesCommitted` evidence, then workLog prose.
   An empty `endingCommit` alone is survivable if a SHA appears in one of the
   other two. When none of the three carries one, the episode lands with
   `commits: 0` and `files_changed > 0`. That shape trips the episode-store
   ratchet in
   `tests/skills/memory/test_extract_session_episode.py::TestValidateModeRejectsUnusableEventIds::test_the_committed_episode_store_is_clean`,
   which runs inside the `python-tests` pre-push job and rejects the ref only
   after the full suite has burned ~18 minutes. Standalone
   `validate_session_json.py` is seconds and catches nothing here; the ratchet
   costs the whole suite. After setting the SHA, regenerate the episode with
   `extract_session_episode.py <log> --preserve` and commit both.

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

- `.agents/schemas/session-log.schema.json`. What a session log contains.
- `scripts/validation/git_hook_policy.py`. The `session` subcommand that
  validates a staged log; it passes when none is staged.
- `scripts/validate_session_json.py`. The reachability check on `endingCommit`.
- Issue #3618. The amend-breaks-endingCommit report.
