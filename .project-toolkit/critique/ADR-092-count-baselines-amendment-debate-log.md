# ADR Debate Log: ADR-092 Amendment 2026-09-29, Count Baselines Derive From the Merge Base

## Summary

- **Rounds**: 1 of 10 (Phase 1 independent review plus one convergence vote)
- **Outcome**: Concluded Without Consensus. Four roles Block on two P1 text findings.
- **Final Status**: needs-revision. The frontmatter stays `status: accepted`; the amendment text needs two edits before merge.
- **Review independence**: one model played all six roles in separate passes. This is not six independent reviews. Treat the votes as one reviewer's six lenses.
- **Artifact reviewed**: `.project-toolkit/architecture/ADR-092-omit-plugin-manifest-version.md`, section "Amendment 2026-09-29: count baselines derive from the merge base" (lines 230 to 251) and the edited sentence at lines 158 to 159.
- **Ground truth**: working tree of branch `fix/5363-ratchet-base-ref` against `origin/main` at `4f43bb189` (41 files, 780 insertions, 1672 deletions). New untracked files `scripts/ci/base_derived_ratchet.py`, `tests/ci/test_base_derived_ratchet.py`, `tests/ci/test_merge_tree_ratchet_behind_base.py`.
- **Owner decision under review**: option B from issue #5363. Delete the count-ratchet scalar and derive the ceiling from the base ref.

## Phase 0: Related Work

| Item | State | Relevance |
|---|---|---|
| #5363 | open, 0 comments | The work item. Its "must not regress" clause says a higher number reaches `main` only through a diff that writes it. |
| #4345 | closed 2026-08-03 | Names the concurrent-admission hole the amendment cites. Its body records `strict_required_status_checks_policy: false`, so admission is not serialized. Citation is accurate. |
| #4171 | referenced | The shared-line conflict class the amendment closes for four ratchets. |
| #5542 | open | Memory about taste-baseline slack; its subject changes once the taste baseline file is gone. |

## Evidence Gathered

- `base_derived_ratchet.py:211-218` returns exit 2 with no `--base-ref`. Matches the table row at ADR line 244.
- `base_derived_ratchet.py:172-178` returns exit 3 with `FORK POINT UNREADABLE` when `_fork_point` is None. Matches line 245.
- `base_derived_ratchet.py:179-185` returns exit 0 with a `bootstrap.` message when the fork lacks the ratchet's own script. `introduced_at` delegates to `baseline_absent_at_ref` (`count_ratchet.py:441-471`), which answers True only when the ref resolves and the path is absent. Matches line 246.
- `base_derived_ratchet.py:186-192` returns exit 3 when the fork tree cannot be measured. Matches line 247.
- `merge_tree_ratchet_check.py` `_check_base_derived` measures the merged tree against `measure_commit(repo_root, base_oid, ...)` for the four registry entries whose `baseline_path` is None (`merge_tree_ratchet_registry.py`). Matches line 234.
- Tests: `uv run --frozen --extra dev python -m pytest tests/ci/test_base_derived_ratchet.py tests/ci/test_merge_tree_ratchet_check.py tests/ci/test_merge_tree_ratchet_behind_base.py` returned 41 passed in 5.27s.
- Counter timing, one warm run each on this machine via each module's `current_count`: ruff 0.2s, taste 3.3s, type-ignore 0.1s, memory-index 0.3s, cli-exit-contract 5.9s, subprocess-encoding 22.6s.
- Workflows: the non-PR legs in `pytest.yml` and the ratchet steps in `pr-validation.yml` set `BASE_REF` to the default branch. Neither `actions/checkout` step in `pr-validation.yml` sets `ref:`.

## Phase 1: Independent Reviews

### architect

Strengths: the amendment follows ADR-092's own precedent (delete the shared line rather than automate writes to it). It names the owning module, the four covered ratchets, the two excluded ones, and every non-pass state. The state table matches code line for line.

Weaknesses: ADR line 238 says the ceiling "can only fall as fast as `main` does". Code does not support "only fall". The ceiling is whatever the fork tree measures, so it rises whenever `main` rises. The amendment's own Known gap (line 251) and #4345 name two ways a regression reaches `main`. The ADR also leaves the "Scope: which conflict class this closes" section (lines 218 to 228) saying `taste_count_baseline.txt` remains and is out of scope, while line 159 was edited to point forward. A reader meets two contradicting sentences.

Zimmermann: Q1 yes, Q2 options come from #5363 and are sound, Q5 yes for the mechanism, Q6 not fully objective (line 238), Q7 actionable, no review date.

| Issue | Priority | Description |
|---|---|---|
| A1 | P1 | Line 238 claims monotone fall; code tracks `main` in both directions. |
| A2 | P2 | Lines 218 to 228 still describe the taste baseline as remaining; add a forward pointer like line 159. |

### critic

Strengths: every explicit state has a test (`test_a_missing_base_ref_is_a_config_error`, `test_unrelated_history_has_no_fork_point`, `test_a_shallow_clone_gets_the_fetch_remedy`, `test_a_fork_point_without_the_ratchet_is_the_bootstrap_case`, `test_a_counter_that_fails_only_on_the_fork_tree_is_an_external_error`).

Weaknesses: the Scope rationale at line 249 says the two excluded ratchets each take "tens of seconds to count". Measured: cli-exit-contract 5.9s, subprocess-encoding 22.6s, taste (included) 3.3s. The rationale is false for one of the two and does not separate cli-exit-contract from taste. The same sentence is in `templates/rules/ci-scripts.md:47`. The scope limit itself stands on the first reason (the issue named four).

Completeness of states: the table omits "current tree cannot be counted", which exits 3 at `base_derived_ratchet.py:220-223`. A typo'd `--base-ref` also lands in `FORK POINT UNREADABLE` because `_fork_point` (`count_ratchet.py:572-577`) returns None on any `merge-base` failure, and the message then blames unrelated history.

| Issue | Priority | Description |
|---|---|---|
| C1 | P1 | Line 249 timing claim contradicted by measurement (cli-exit-contract 5.9s). |
| C2 | P2 | Table omits the "branch tree cannot be counted, exit 3" state. |
| C3 | P2 | Nonexistent base ref is reported as unrelated history; the row's cause list is incomplete. |

### independent-thinker

Challenge: is the Known gap honestly stated? The sentence is true as far as it goes: on push to `main`, `git merge-base HEAD main` is HEAD, so the standalone run compares HEAD with itself. What it leaves out is the consequence that changed with option B. Under the scalar, a regression that reached `main` made every later branch red until someone fixed it, which is loud. Under option B, the same regression becomes the ceiling for every later branch with no signal anywhere. #4345 records that admission is not serialized, so this path is live, not theoretical. The issue's own "must not regress" clause is about exactly this. Option B is the owner's call and the amendment says "no recorded floor"; it should also say "a regression that reaches `main` is absorbed silently".

Contrarian check on scope: limiting to four is sound on the owner's framing. Moving cli-exit-contract later costs one more measurement of about 6s; that is a separate decision, as the ADR says.

| Issue | Priority | Description |
|---|---|---|
| I1 | P1 | Known gap omits silent absorption of a regression that reaches `main` (same root as A1). |
| I2 | P2 | In PR CI, `actions/checkout` with no `ref:` checks out the synthetic merge commit (INFERRED from the action's documented default, not run here), so the standalone leg measures merged tree against base tip, not branch against fork. Line 233 describes the local shape only. |

### security

Threat surface: the counter and tool config come from the branch and are applied to both trees. A branch that weakens the counter lowers both counts equally. That was already true under the scalar, so trust did not change. `measure_commit` materializes into a `tempfile.mkdtemp` scratch, strips `GIT_*` through `git_environment()` (test `test_a_foreign_git_dir_in_the_environment_does_not_redirect_the_read`), and returns None when cleanup fails. No secret or token handling added. Fail-closed on every unmeasurable state is correct.

| Issue | Priority | Description |
|---|---|---|
| S1 | P2 | Silent absorption (I1) is also a bypass-persistence path: one admin-bypass merge permanently raises the ceiling. Stating it in the ADR is sufficient. |

### analyst

Verified the four-state table against code and tests; all four rows match. Verified the merge-tree claim against `_check_base_derived`. Verified #4345 citation. Measured counter costs (above). Confirmed C1 by measurement and A1 by reading `_ceiling`: nothing reads any stored floor.

| Issue | Priority | Description |
|---|---|---|
| N1 | P1 | Same as C1. |
| N2 | P2 | `templates/rules/ci-scripts.md:94` still opens "A count ratchet may only fall", which is now true only for the two scalar ratchets. |

### high-level-advisor

Priority call: option B is the right trade for the owner's stated goal and the code implements it with fail-closed states and tests. The two P1 findings are text accuracy, not design defects. They are cheap to fix and must be fixed, because this ADR is the record a later reader uses to decide whether a regression on `main` is possible. Do not re-open option A or C.

## Phase 2: Consolidation

Consensus points: code matches the four-state table; scope to four is sound on the issue's naming; the mechanism removes the shared-line conflict class for those four.

Conflicts: none on direction. Severity of A1/I1 debated: high-level-advisor ranks it text-only; independent-thinker ranks it the one thing a future maintainer most needs. Ruling: P1, text fix required.

Anti-pattern check: no role produced editorial-only findings. The critic's C3 is close to Copy Edit but names a real misdiagnosis path, so it stays P2.

## Phase 3: Proposed Resolutions

| Finding | Resolution proposed to the ADR author |
|---|---|
| A1, I1 (P1) | Replace line 238's "so it can only fall as fast as `main` does" with text saying the ceiling tracks `main` both ways, and add to Known gap: a regression that reaches `main` (bypass, #4345 concurrent admission) becomes the ceiling for later branches with no alarm. |
| C1, N1 (P1) | Replace "each takes tens of seconds to count" at line 249 with the measured shape (subprocess-encoding about 20s; cli-exit-contract a few seconds) or drop the cost reason and keep "the issue did not name them". Mirror in `templates/rules/ci-scripts.md:47`. |
| A2, C2, C3, I2, S1, N2 (P2) | Documented here; non-blocking. |

The reviewer did not edit the ADR. No resolution is applied yet.

## Phase 4: Convergence Vote (Round 1)

| Agent | Position | Notes |
|---|---|---|
| architect | Block | A1 open: line 238 states a monotone fall the code does not have. |
| critic | Block | C1 open: line 249 timing claim is false for cli-exit-contract. |
| independent-thinker | Block | I1 open: Known gap omits silent absorption on `main`. |
| security | Disagree-and-Commit | Wants S1 stated; not blocking alone. |
| analyst | Block | N1 open, measured. |
| high-level-advisor | Disagree-and-Commit | Decision sound; the text must change before merge. |

Result: 0 Accept, 2 Disagree-and-Commit, 4 Block. Consensus NOT reached. This is not agreement.

## Next Steps

The ADR author applies the two P1 text edits, then a second round re-votes. No issue was filed by this review.

## Round 2: Re-verification of P1 Findings

Same reviewer, same single-model caveat: one model played all six roles. Each claim below was checked against the working tree by grep and diff, not taken from the author's summary.

| Finding | Evidence in the file | State |
|---|---|---|
| A1, I1 | ADR line 238 now reads "so it follows `main` in both directions". Line 252 adds that a regression reaching `main` by a bypass merge or two PRs admitted together "becomes the ceiling for every later branch with no alarm", and that the old scalar made the next PR fail instead. | Closed |
| C1, N1 | ADR line 250 now gives measured figures: cli-exit-contract 5.9s, subprocess-encoding 22.6s, against 0.1s to 3.3s for the four moved. "tens of seconds" is gone from the ADR and from line 47 of `templates/rules/ci-scripts.md`, `src/claude/rules/ci-scripts.md`, `.claude/rules/ci-scripts.md` and `.github/instructions/ci-scripts.instructions.md`. The template and both `.claude` copies are byte-identical (`diff -q` silent). | Closed |

P2 status after round 2:

- A2 closed: lines 221 to 222 now say the taste baseline is deleted by the amendment.
- C2 closed: line 248 adds "Branch tree cannot be counted | Exit 3."
- N2 closed: the Count ratchets heading now reads "A count may not exceed the merge base, or the recorded baseline for the two scalar ratchets." The remaining "may only fall" at rule line 57 describes cli-exit-contract, which is still scalar, so it is accurate.
- C3 open: a mistyped `--base-ref` still reports unrelated history. Non-blocking.
- I2 open: the PR CI merge-commit checkout shape is not described. INFERRED, non-blocking.
- S1 closed by the new Known gap text.

The ADR still contains 0 em or en dashes.

### Agent Positions (Round 2)

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | A1 and A2 closed in the text. |
| critic | Accept | C1 and C2 closed; C3 recorded as P2. |
| independent-thinker | Accept | I1 closed; I2 recorded as P2. |
| security | Accept | S1 now stated in Known gap. |
| analyst | Accept | N1 and N2 verified by grep and diff. |
| high-level-advisor | Accept | No blocking text remains. |

Result: 6 Accept, 0 Disagree-and-Commit, 0 Block. Consensus reached in round 2 of 10. The single-model caveat above still applies: this is one reviewer's six lenses, not six independent reviews.
