# ADR Debate Log: ADR-092 Explicit States Table, Bootstrap Row (Issue #6145)

## Summary

- **Rounds**: 1 of 10 (Phase 1 independent review plus one convergence vote)
- **Panel**: reduced, architect and critic. The edit is a prose table change in the amendment. It changes no executable enforcement and no rule another gate reads.
- **Outcome**: Consensus. Both roles Accept.
- **Final Status**: accepted. The frontmatter `status: accepted` is unchanged.
- **Review independence**: one model played both roles in separate passes. This is not two independent reviews. Treat the votes as one reviewer's two lenses.
- **Artifact reviewed**: `.project-toolkit/architecture/ADR-092-omit-plugin-manifest-version.md`, the "Explicit states" table of the 2026-09-29 amendment (lines 243 to 251).
- **Owner decision under review**: none. The ADR decision stands. Only the table text changes, to match code that PR #6108 changed.

## Phase 0: Related Work

| Item | State | Relevance |
|---|---|---|
| #6145 | open | The work item. The bootstrap row names one condition and the code needs two. |
| #6108 | merged | Added `ratchet_registry_at_ref.py`, the `RATCHET REMOVED` and `RATCHET SCRIPT MOVED` failures, and the label condition on bootstrap. |
| #5363 | closed | Origin of the amendment. Its earlier debate log is `ADR-092-count-baselines-amendment-debate-log.md`. |

## Evidence Gathered

- Before the edit, the row read "Fork point lacks the ratchet's own script | Bootstrap". The ADR was last touched by #6108 (`1aad4cc46`) and that change did not edit this row.
- `scripts/ci/base_derived_ratchet.py:340` enters the bootstrap branch only when `label not in entries and introduced_at(root, fork, introduced_by)`. Both conditions are required. `entries` is the registry read at the fork point.
- `base_derived_ratchet.py:343` prints `BOOTSTRAP REFUSED` and returns `EXIT_REGRESSION` (1) when the branch registry does not map the label to `introduced_by`.
- `base_derived_ratchet.py:337` returns `EXIT_REGRESSION` (1) when `registry_drift` reports a problem. `ratchet_registry_at_ref.py:109` and `:115` emit `RATCHET REMOVED` and `RATCHET SCRIPT MOVED`.
- `base_derived_ratchet.py:331` prints `REGISTRY UNREADABLE` and returns `EXIT_EXTERNAL` (3).
- `count_ratchet.py:79` and `:81` set `EXIT_REGRESSION = 1` and `EXIT_EXTERNAL = 3`.
- Tests: `uv run --frozen --extra dev python -m pytest tests/ci/test_base_derived_ratchet.py tests/ci/test_ratchet_registry_at_ref.py -n 2 -q` returned 37 passed in 1.99s. `test_base_derived_ratchet.py:166` and `:178` assert `BOOTSTRAP REFUSED`. `test_ratchet_registry_at_ref.py:76`, `:87` and `:110` assert `RATCHET SCRIPT MOVED`, `RATCHET REMOVED` and `REGISTRY UNREADABLE`.
- Mirrors: `git grep` for the old row text found it only in the ADR. The rule text in `templates/rules/ci-scripts.md:43` already states both bootstrap conditions and the removed and moved failures.

## Phase 1: Independent Reviews

### architect

Strengths: the fix keeps the table's shape (one state, one result) and adds no prose outside it. The new rows follow the order the code checks them: fork point, registry read, registry drift, bootstrap, tree measure. The ADR decision is untouched.

Weaknesses: the old row is the only state a reader uses to decide whether a new ratchet may land without a ceiling, and it was wrong in the dangerous direction. It implied that a missing script alone bootstraps. A ratchet whose label the fork already registers, with its script deleted from the fork, would be read as bootstrap by the table and as `RATCHET REMOVED` by the code.

| Issue | Priority | Description |
|---|---|---|
| A1 | P2 | Rule text `ci-scripts.md:43` omits `BOOTSTRAP REFUSED` and `REGISTRY UNREADABLE`. Outside this issue. Flagged in the PR body. |

### critic

Strengths: every claim in the three changed rows traces to a code line and a passing test, listed above. Exit codes match `count_ratchet.py:79` and `:81`.

Weaknesses checked: the issue asks for the one row. Adding the removed-or-moved row and the unreadable row goes past the literal text. Ruling: keep them. The table is titled "Explicit states", the prior review closed finding C2 by adding a missing exit-3 state to it, and a table that names `BOOTSTRAP REFUSED` without the sibling failures that share the same registry read leaves the reader unable to tell what a registry label does at the fork point. Three rows, one source (#6108), one table.

Not claimed: the table does not say what happens when the label is absent from the fork registry and the script is present at the fork. That case falls through to measuring the fork tree, which the existing "Fork tree cannot be measured" row covers on failure. No row is added.

| Issue | Priority | Description |
|---|---|---|
| C1 | P3 | The message wording in the row ("a message that says so") is kept from the original. Non-blocking. |

## Phase 2: Consolidation

Consensus points: the row now matches the code at `base_derived_ratchet.py:331-354`; the extra rows share one source and one table; no enforcement changes.

Conflicts: none.

## Phase 3: Proposed Resolutions

| Finding | Resolution |
|---|---|
| A1 (P2) | Out of scope for this diff. Recorded in the PR body for the owner. |
| C1 (P3) | None needed. |

## Phase 4: Convergence Vote (Round 1)

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Table matches the code order. No decision text changed. |
| critic | Accept | Each row cites a code line and a passing test. |

Result: 2 Accept, 0 Disagree-and-Commit, 0 Block. Consensus reached in round 1 of 10. The single-model caveat above applies.
