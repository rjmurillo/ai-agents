# A post kill pipe read can hang even when the process group lookup works

**Atomicity**: 90%
**Category**: Subprocess handling
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E108. State checked on main at 1be533c496 (2026-11-26).

## Question

Which process cleanup failures from the review reproduced on Linux?

## Conventional answer

A reviewer claimed `_run_command` and `terminate_process_tree` could both lose the group after reaping the child.

## First-principles position

In `_run_command`, the unreaped child still belonged to its process group. That lookup failure did not reproduce. The lookup did fail on the old `terminate_process_tree` path after the child was reaped. An unbounded `communicate()` can also wait on an open pipe after the group kill.

## Evidence with limits

- The old `terminate_process_tree` path lost the group lookup, and a grandchild stayed alive (2026-08-05).
- The `terminate_process_tree` case spent 30.0 seconds in `communicate()` before returning (2026-08-05).
- The unbounded `communicate()` did not return within the external 120-second limit in 2 runs (2026-08-05).
- Limits: Linux only. The session ran the 30-second case once and the hang probe twice. Windows behavior was not tested.
- State on main at 1be533c496 (2026-11-26): still wrong. `scripts/validation/git_hook_policy.py:1064` and `:1076` use unbounded `communicate()` after process group cleanup. `_run_command_bytes` repeats the pattern at `:1118` and `:1130`.

## Decision

Set a timeout on `communicate()` after killing the process group. Abandon the pipes if the read times out. Test group lookup claims on the target OS. The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/eval-harness-observations.md`
