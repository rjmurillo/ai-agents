# An ADR said the matcher shim fails open on malformed stdin, and running the shim showed exit 2

**Atomicity**: 90%
**Category**: Hook contract, fail open policy
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E044. State checked on main at 1be533c496 (2026-11-26).

## Question

Does the require-subagent-model shim fail open on malformed stdin, as the ADRs say?

## Conventional answer

The ADR-071 amendment and ADR-068 said the shim fails open on malformed input, under the issue 4672 policy.

## First-principles position

Running the generated shim showed it fails closed. Fail open held only on the .github/hooks path. The plugin path denies on pre-dispatch input errors and on timed shim timeouts. ADR prose and a source level policy note did not show this.

## Evidence with limits

- Direct execution (2026-08-11): exit code 2 on the input "not json" and on "{}".
- Limits: One hook, one machine, and two invalid inputs. PR 4893 made the shim follow the wrapped hook's policy.
- State on main at 1be533c496 (2026-11-26): fixed. `build/scripts/generate_hooks_shim.py:188` sets `_INPUT_ERROR_CODE` to 0 for fail open and 2 otherwise. ADR-071 lines 299 to 301 now say to allow malformed input.

## Decision

Prove a fail open or fail closed claim by running the generated shim with malformed stdin and reading the exit code with no pipe in the way. Do not trust ADR prose or a source level policy note.

## Related

- `.serena/memories/hooks/require-subagent-model-gate.md`
