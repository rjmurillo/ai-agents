# Raising MAX_BASELINE_SLACK had no runtime effect while only tests called baseline_health

**Atomicity**: 90%
**Category**: CI ratchets
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E115. State checked on main at 1be533c496 (2026-11-26).

## Question

Did raising the slack constant change what the ratchet checked at runtime?

## Conventional answer

The slack increase from 5 to 6 in PR 4648 was credited with fixing merge queue baseline collisions.

## First-principles position

Only tests called `baseline_health`, the function that reads `MAX_BASELINE_SLACK`. The command path checked whether the count exceeded the baseline. Changing the slack constant could not affect that path.

## Evidence with limits

- A search of `scripts/` and `tests/` found calls to `baseline_health` only in tests (2026-08-06).
- The `count_ratchet.py` runtime path returned a regression only when the count exceeded the baseline (2026-08-06).
- Limits: One function in one script. The search established caller coverage but did not reproduce the merge queue collision.
- State on main at 1be533c496 (2026-11-26): fixed. `scripts/ci/count_ratchet.py:1023` calls `baseline_health(count, baseline)`. PR 4644 wired it in on 2026-08-11.

## Decision

Find a runtime caller for the code that reads a constant before crediting a change to it. Exercise that caller when testing the new value.

## Related

- `.serena/memories/decision-every-merge-invalidates-every-open-pr.md`
- `.serena/memories/ci/ci-count-ratchet-never-names-the-offending-file.md`
