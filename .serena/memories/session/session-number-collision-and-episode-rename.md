<!-- placement: evidence; reason: a dated concurrent-allocation collision, its recovery sequence, and an unresolved allocator limitation -->

# Session: Two Branches Allocated the Same Session Number

The session-init skill that this incident was reported against is gone
(commit `ba541c21f`), and `.claude/rules/session-logs.md` discontinues session
log creation. `scripts/validate_session_json.py` is still live, so the field
trap below still applies to a log carried over from an older branch.

## Observation (2026-08-05)

Two branches, `docs/botpat-identity-git-transport-memory` and
`fix/4519-4520-coupling-diffbase`, each filed
`.agents/sessions/2026-08-05-session-9999.json`. The number `9999` appeared
nowhere in `scripts/` or the session-init skill; both agents invented it
independently as an "unknown" placeholder rather than running the allocator.

The merge surfaced as add/add on two files: the session log, and its episode
under `.agents/memory/episodes/`.

## Why merging the two logs is the wrong resolution

The two files describe different sessions on different branches, not one file
that diverged. A merged workLog describes a session that never happened and
falsifies both records. Keep one file intact, re-file the other under a free
number.

## The rename takes two edits, not one

The number lives inside the file as `session.number` as well as in the
filename. `validate_session_json.py` compares the two and fails the mismatch by
name. The field is `session.number`, not `sessionNumber`.

Regenerate the episode from the renamed log rather than renaming the episode by
hand. Each event carries `_source_session`, which the extractor uses for
cross-session deduplication.

## The limitation that made the collision possible

The allocator of the day prevented reuse that was visible in the working tree
or on `origin/main`. It could not see a concurrent unmerged branch in another
worktree, so two agents could still reach the same next number. A filename
suffix keeps episode names distinct when objectives differ, but numeric
uniqueness needs a shared atomic reservation or a collision-resistant
identifier. Neither exists.

## Related

- [session-writing-todo-in-evidence-trips-the-contradiction-scanner](session-writing-todo-in-evidence-trips-the-contradiction-scanner.md)
- [session-protocol-validator-pipe-bug](session-protocol-validator-pipe-bug.md)
