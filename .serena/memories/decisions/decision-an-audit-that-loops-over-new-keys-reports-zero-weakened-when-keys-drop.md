# An audit of surviving baseline keys misses entries that disappear

**Atomicity**: 90%
**Category**: CI ratchets
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E112. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a zero WEAKENED report prove that baseline regeneration kept its coverage?

## Conventional answer

A zero WEAKENED result was given as the all-clear for portability baseline regeneration.

## First-principles position

The audit loop inspected only keys in the new `files` map. A deleted key never reached the loop. Moving a file out of that map removed its references without changing the WEAKENED count.

## Evidence with limits

- A simulation on baseline `ad4d20e985` moved `src/copilot-cli/skills/spec/SKILL.md` to `marker_files` (2026-08-01).
- The simulated file count fell from 73 to 72, and undeclared references fell from 204 to 163 (2026-08-01).
- The published audit snippet still reported `files WEAKENED: 0` (2026-08-01).
- Limits: The probe ran in memory and wrote nothing. The snippet appeared in a fleet notice and PR text.
- State on main at 1be533c496 (2026-11-26): superseded. `scripts/validation/portability_baseline.py:85` refuses to drop a `files` entry unless the caller allows baseline shrinkage.

## Decision

Compare old baseline keys against new ones and check the total references. Track removed keys separately from weakened entries that survive.
