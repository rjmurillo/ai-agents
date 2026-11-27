# A repair guard that compares edge counts accepts a repair that drops most original edges

**Atomicity**: 90%
**Category**: Guard design, causal graph repair
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E010. State checked on main at 1be533c496 (2026-11-26).

## Question

Does an edge count comparison prove a graph repair lost no edges?

## Conventional answer

The fix repair restores git ground truth with zero edges lost and refuses edge loss, so the council's objection was wrong.

## First-principles position

The timestamp fixes were exact, but the edge claim was false. The guard compares only counts. New edges can outnumber lost ones, so the totals look fine while most original edges are gone.

## Evidence with limits

- Measured 2026-08-02 on 12 episode files: 63 of 63 repaired timestamps equal the git instants.
- Edge totals went from 192 old to 207 new, yet 167 of 192 old edges were absent from the new set.
- All 12 repairs ran with no refusals, because the guard compares only totals.
- Limits: One PR (PR 4219) and 12 episode files (2026-08-02). The sweep checked main by source only. `_real_edge_count` skips edges from synthetic midnight events. Some of the 167 may no longer count as real edges.
- State on main at 1be533c496 (2026-11-26): still wrong. `src/claude/skills/memory/scripts/extract_session_episode.py:2639` subtracts edge totals. The help at line 1947 still promises to refuse any repair that drops edges.

## Decision

A guard that rejects edge loss must compare edge identities. Check that every old edge appears in the rebuilt set.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/retrospective/retrospective-001-pr-learning-extraction.md`
