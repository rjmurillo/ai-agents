# ADR Debate Log 5: ADR-126 Two-Copy Correction

## Summary

- **Prior debate log**: [4](ADR-126-debate-log-4.md), closed by consensus.
- **Rounds**: 1.
- **Outcome**: Consensus. Architect voted Accept. Critic voted Disagree-and-Commit.
- **Final Status**: unchanged (`proposed`). No decision changed.
- **Panel**: reduced, architect and critic. The edit changes ADR prose and the
  claims ledger only. No executable enforcement or gate-read rule changed.
- **Claims ledger**: [ADR-126 claims ledger](ADR-126-claims-ledger.md), rows 32 to 37.

## Change under review

The `/review` round 16 architect axis on branch `fix/agent-readiness-signals`
found ADR-126 stale. Commit `3ed94c402` (2026-11-24) made
`store_resolution.py` import its root and store rules from
`memory_core.memory_store`. The ADR still said three source copies. It also
said `search_memory.py` may not import `memory_core`.

The amendment says two copies in Forces, Decision 4, Consequences, Security,
and Confirmation. It adds an `## Amendment 2026-11-25` section.

## Round 1

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Critic | P1 | Rollback named two copies and the hook. `resolve_stores` reads notes and computes the shadow on its own (`store_resolution.py:65-69`). | Rollback now names `store_resolution.resolve_stores` |
| Critic | P2 | Security no longer said where the episode-store root check lives (`store_resolution.py:61-64`) | Security names the `resolve_stores` episode check |
| Architect, Critic | P2 | Confirmation counted `store_resolution` as its own leg of the root test. It re-exports the skill copy. | Bullet says both copies and the hook; notes the re-export |
| Architect, Critic | P2 | Forces read as a non sequitur and overstated what the gate accepts | Forces gives both reasons and names the `dirname(__file__)` idiom |
| Architect, Critic | P2 | The cited range `import_closure.py:25-28` stopped mid-sentence and cited only the docstring | Cites `25-31` and `_sys_path_inserts` at line 245; ledger row 35 matches |
| Critic | P2 | Two long sentences, one in Decision 4 and one in the ledger | Both split |

## Gate results

- Claims ledger rows 32 to 37: VERIFIED. Row 34 was refuted by the refuting
  seat as first worded, then corrected with a grep that matches both names.
- Refuting seat (analyst, haiku): two runs, recorded in the ledger.
- Self-consistency: VERIFIED after the round 1 fixes.
- `check_surface_parity.py`: exit 0. `test_memory_root_parity.py`: 32 passed.

## Dissent

Critic (Disagree-and-Commit): the first draft understated rollback scope and
left the episode check unplaced. Both are fixed above.

## Not changed

- An identity test (`store_resolution.find_memory_root is
  memory_store.find_memory_root`) would lock the "holds no copy" claim. Critic
  marked it optional. It is not added here.
- `ADR-126-debate-log-2.md` still says three copies. It is a historical record.

## Citation repair (2026-11-25)

Commit `fbb7ac83d` moved `_sys_path_inserts` out of `import_closure.py`.
It is now `sys_path_inserts` in `build/scripts/import_closure_paths.py:59`.
The ADR citation follows the code. No decision text changed.
