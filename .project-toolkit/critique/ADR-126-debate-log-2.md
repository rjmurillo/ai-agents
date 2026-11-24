# ADR Debate Log 2: ADR-126 Store Module Locations

## Summary

- **Prior debate log**: [ADR-126 debate log](ADR-126-debate-log.md), closed by consensus.
- **Rounds**: 1
- **Outcome**: Consensus. The architect voted Disagree-and-Commit; the critic
  voted Block, then Accept on re-vote after its P1 fixes landed.
- **Panel**: reduced, architect and critic. The revision moves code locations
  and citations; the decision is unchanged.
- **Claims ledger**: [ADR-126 claims ledger](ADR-126-claims-ledger.md), rows 4,
  5, 8, and 16 to 18.

## Change under review

The import-closure gate (issue #7221) rejected `search_memory.py` importing
`memory_core`. The store rule now has three source copies: the repository
package `stores.py`, the router's `memory_store.py`, and the search script's
sibling `store_resolution.py`. Line-number citations became symbol names.

## Round 1

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Architect | P1 | The ADR stated the import gate as "only a module beside it", hiding the `lib/` option | Gate stated in full; the ADR says why `lib/` was not used |
| Critic | P1 | Confirmation cited a renamed test | Renamed to `test_hook_and_skill_choose_the_same_root`; ledger row 17 checks all 14 names |
| Critic | P1 | Implementation Notes said only two files ship | Now names both sibling modules |
| Both | P2 | "One per runtime" was wrong; source copies vs build mirrors unclear | "One per import boundary", plus a mirror sentence |
| Critic | P2 | Negative consequence still blamed "stdlib-only" | Reworded to the real cause |
| Critic | P2 | Shadow rule location not stated | Named in the `stores.py` and `store_resolution.py` bullets |
| Both | P2 | Docstrings in `stores.py` and the parity test said "two copies" | Both now name three |
| Architect | P2 | Ledger lacked the import-gate claim; row 8 grep was stale | Rows 8 and 16 updated and added |
| Architect | P2 | Long lines and a repeated hooks sentence | Rewrapped and removed |

## Round 1 re-vote

The critic re-checked the revised files and voted Accept. It raised four P2s:
ledger row 5 lacked `shadowed_notes_dir`, the ledger header and row count were
stale, one Negative consequence kept the narrow gate wording, and this log
recorded consensus before the re-vote. All four are fixed. The architect's
Disagree-and-Commit stands; its P1 on the gate wording is resolved.

## Verdict

Consensus: architect Disagree-and-Commit, critic Accept.
