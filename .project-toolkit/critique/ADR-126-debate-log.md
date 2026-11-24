# ADR Debate Log: ADR-126 Repository-Resolved Memory Store

## Summary

- **Rounds**: 2
- **Outcome**: Consensus. Both seats voted Disagree-and-Commit in round 2.
- **Final status**: proposed. The owner chose this ADR (decision D1 on
  2026-11-23); acceptance is the owner's call at merge.
- **Panel**: reduced, architect and critic. The change touches no executable
  enforcement and no rule another gate reads.
- **Claims ledger**: [ADR-126 claims ledger](ADR-126-claims-ledger.md).

## Change under review

- New record ADR-126 amends ADR-106 Decisions 2 and 5 by reference.
- ADR-106 gains an `**Amended by**:` footer, per the
  [amended-by backfill](ADR-106-amended-by-backfill-debate-log.md) convention.
  Its body is unchanged.

## Round 1

Architect voted Disagree-and-Commit. Critic voted Block.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Critic | P0 | Shipped `memory_router.py` read only `.serena/memories`, contradicting Decisions 1 and 2 | `resolve_memory_store` added; `search_memory` resolves per call; three router tests |
| Both | P1 | Amend by reference left no pointer in ADR-106 | `**Amended by**:` footer added to ADR-106 |
| Both | P1 | Shadowed notes were silent, including the empty-folder case | Decision 1 states the folder-exists rule; search diagnostic and SessionEnd report shadowed notes |
| Critic | P1 | "Retrieval never reads both" was untested per entry point | One both-folders test each for search, recall hook, and router |
| Both | P1 | Decision 5 claimed more than the code did | Narrowed to the prompt recall hook |
| Architect | P1 | No Security Considerations or Confirmation section | Both added |
| Both | P2 | Third copy of the store paths in `serena_integration.py`; ADR-063 relationship; Decision 3 note; which paths ship; missing alternatives; unused `find_repo_root` export | Constant reused; ADR-063 stated unchanged; notes and alternatives added; export and function removed |

## Round 2

Architect voted Disagree-and-Commit. Critic voted Disagree-and-Commit.
Every round 1 finding was verified as resolved against the files.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Architect | P1 | Store selection is copied three times but only root selection had a parity test | `test_every_picker_chooses_the_same_store` over five layouts and a containment test; Decision 4 names both rule sets |
| Critic | P1 | `memory-router.md` still described a Serena-only store in its diagram, defaults, example, and troubleshooting | Rewritten to the resolved store |
| Critic | P1 | Decision 2 claimed every memory skill works on either folder; eight maintenance scripts assume the Serena layout | Decision 2 narrowed and the scripts named |
| Critic | P2 | The write-guard partial told agents to edit `.serena/memories/`, which would create the folder and shadow notes | Partial and its 11 inline copies now say "the repository memory files" |
| Architect | P2 | Router started from the current directory while search started from `CLAUDE_PROJECT_DIR` | Router now prefers `CLAUDE_PROJECT_DIR`, with a test |
| Architect | P2 | Security section overstated containment for explicit paths | Reworded: explicit paths are trusted as given |
| Critic | P2 | Search diagnostic lacked the `git mv` step the ADR claimed | Added, with a test |
| Critic | P2 | Empty-Serena rule tested only through the CLI | `test_empty_serena_folder_shadows_notes_on_every_entry_point` |
| Critic | P2 | Router labeled notes results `Serena` | Results from the notes store carry `RepositoryNotes` |
| Architect | P2 | ADR-106 footer lacked the `---` separator | Added |
| Architect | P2 | Dead fallback line in `search_memory.py` | Removed |
| Critic | P2 | ADR dates read 2026-11-24 while the machine date is 2026-11-23 | Dates corrected to 2026-11-23 |

## Recursive defect found during review

The critic ran `improve_memory_graph_density.py` in a fixture whose git lookup
failed. The script then walked up from its own file and rewrote two files in
this checkout's `.serena/memories/`. The critic restored them. The same fallback
existed in `convert_index_table_links.py` and `convert_memory_references.py`.
All three now walk up from the current directory and fail when no checkout is
found. `tests/skills/memory/test_project_root_fallback.py` pins both cases.

## Dissent recorded

- Architect: the parity tests are the only guard on three copies of each rule.
  Accepted as the cost of two stdlib-only shipped modules.
- Critic: corpus maintenance scripts still assume the Serena layout. Accepted
  and recorded in Decision 2 and the Negative consequences.

## Verdict

Consensus by Disagree-and-Commit from both seats. No blocking position remains.
