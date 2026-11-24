# ADR Debate Log: Citation Renumbers After the Apache 2.0 Relicense

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: frontmatter-one-parser-citation-renumber-debate-log.md
- **Outcome**: Consensus
- **Final Status**: accepted

Reduced panel: architect and critic. The change touches no executable enforcement
and no rule another gate reads. It only renumbers `path:line` citations, so
AGENTS.md calls for the reduced panel.

Scope: ADR-100 and ADR-102. The branch `chore/relicense-apache-2.0` adds
`"NOTICE"` to two allowlists near the top of `scripts/validation/git_hook_policy.py`,
which moves every later line down by 2. It also adds two entries to
`FORKED_COMPONENTS` in `scripts/generate_third_party_notices.py`, which moves
later lines down by 20. `scripts/validation/citation_reverse_pass.py` flagged the
citations below as newly stale. No decision, status or prose meaning changes.

## Round 1 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept, after five missed non-ADR citations were re-anchored |

### Key Issues Addressed

- Both seats read each new line number and confirmed it holds the code the
  citing sentence quotes.
- ADR-100:37 cited `:6373` and `:6389`. At the merge base the quoted code sat at
  6852 and 6868, so both numbers were already wrong. The gate accepted `:6389`
  at base only because the short anchor " and" matched a comment there. The
  sentence describes live code, so both numbers now point at the quoted lines,
  6854 and 6870. The critic ruled out an ignore marker: that precedent covers
  citations to a deleted gate, and this code still exists.
- The critic found five non-ADR citations the gate did not flag. Each was right
  at base and is now 2 lines low. All five were re-anchored in the same change.

### Final Diff

| Citing line | Old | New |
|-------------|-----|-----|
| ADR-100:37 | `git_hook_policy.py:6373` and `:6389` | `:6854` and `:6870` |
| ADR-102:221 | `git_hook_policy.py:2785` | `2787` |
| ADR-102:355 | `git_hook_policy.py:2785` | `2787` |

The same change fixes these non-ADR citations:

- `build/scripts/generate_adr_index.py:1012`
- `scripts/validation/citation_head_state.py:91`
- `scripts/validation/check_push_lock_before_commit.py:49`
- `.agents/governance/FAIL-OPEN-INVENTORY.md:103`, `:116`, `:119` and `:151`

## Round 2 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept, unchanged; the marker restates facts both seats verified in round 1 |
| critic | Accept, unchanged; round 1 already named this citation as historical |

### Key Issues Addressed

- The reverse-pass gate treats a line this branch edits as owning all its
  citations. ADR-100:37 also cites the deleted `_check_commit_limit` at
  `:6727`, which was already wrong at base.
- That citation is history, the same case ADR-100:256 handles. It now carries
  the same kind of inline `citation-freshness: ignore` marker, naming the
  commit where the line matched and the commit that deleted the gate.
- `git show 72f0e6309:scripts/validation/git_hook_policy.py` line 6727 reads
  `def _check_commit_limit(`, and 23ad6e429 (2026-09-22) deleted the gate.

### Next Steps

The panel noticed these lines were already wrong at base. They stay out of
scope for this change:

- ADR-100:31, :180, :250 and :436
- ADR-101:84
- ADR-102:112
