# Moving a directory deletes almost nothing, so it earns no subtraction credit

**Atomicity**: 90%
**Category**: Release gates, subtraction
**Source**: Agent session sweep, sessions dated 2026-09. Sweep ids E089. State checked on main at 1be533c496 (2026-11-26).

## Question

Does relocating a directory count toward a control-plane subtraction release gate?

## Conventional answer

The epic ledger first classed the move of the `.project-toolkit/` directory (issues 5420 and 5421) as DELETE. Relocation counted toward the subtraction gates.

## First-principles position

The proposed move deleted one empty file and no bytes (2026-09-17). It kept the live files and required updates to code that reads them. The ledger changed the row from DELETE to EXPERIMENT.

## Evidence with limits

- A move would delete 1 file and 0 bytes (`checkpoints/.gitkeep`) (2026-09-17).
- The same move would relocate about 5.9 MB across 1,166 live files, with at least 14 reader sites to re-point (2026-09-17).
- Limits: One issue, one date (2026-09-17). Counts are static file sums, not a runtime measure.
- State on main at 1be533c496 (2026-11-26): no repo artifact records the subtraction rule. `validate_investigation_claims.py:145` notes that a byte-identical rename, such as the issue 5420 root move, is not authorship.

## Decision

Count subtraction by bytes and files removed. A relocation moves bytes and adds reader risk, so it does not satisfy a subtraction gate.
