# A merge tree ratchet needs the lower of the base and merged baselines

**Atomicity**: 90%
**Category**: CI ratchets
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E162. State checked on main at 1be533c496 (2026-11-26).

## Question

Which baseline should a scalar ratchet use when checking a proposed merge?

## Conventional answer

Checking the merged tree against the base branch baseline was thought to catch concurrent regressions.

## First-principles position

The proposed merge lowered the Ruff baseline. A concurrent merge added suppressions first. The gate passed the merged count against the old ceiling, even though the proposed ceiling was lower. Reading both baselines caught the regression.

## Evidence with limits

- PR 4208 lowered the baseline from 308 to 126, and a concurrent commit landed 14 suppressions first (2026-08-04 replay).
- On base `287aa9400` and head `3fffdd4fc`, the old gate passed 140 against 308 (2026-08-04 replay).
- On the same pair, the new gate rejected 140 against 126 (2026-08-04 replay).
- Limits: One Ruff incident, with Ruff pinned to 0.15.16 throughout. The related merge freshness memory records the same event from the receiving PR's side.
- State on main at 1be533c496 (2026-11-26): fixed. `scripts/ci/merge_tree_ratchet_check.py:246` returns `min(base_value, merged_value)`.

## Decision

Use the lower of the base and merged tree baselines as the ceiling. Replay the gate on the real base and head commits before claiming it prevents the race.

## Related

- `.serena/memories/decision-every-merge-invalidates-every-open-pr.md`
- `.serena/memories/ci/run-count-ratchets-before-the-expensive-pre-push.md`
