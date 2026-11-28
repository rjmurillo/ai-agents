# ADR Debate Log: ADR-104 Amendment (2026-11-27): Retire CI-Owned Heavy Passes From Pre-Push

Prior debate log: `.project-toolkit/critique/ADR-104-prepush-pytest-removal-debate-log.md`
Claims ledger: `.project-toolkit/critique/ADR-104-ci-owned-heavy-passes-claims-ledger.md`
Target ADR: `.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md`

## Summary

- **Rounds**: 2 of 10
- **Review Panel**: 6 independent seats (`architect`, `critic`, `independent-thinker`, `analyst`, `security`, `high-level-advisor`), Sonnet, read-only
- **Outcome**: Consensus in round 2 (5 Accept, 1 Disagree-and-Commit). Status stays `accepted`; this amendment does not change the frontmatter enum.
- **Scope**: the `## Amendment 2026-11-27` section, rule 2, the Status paragraph, the Consequences pointer, and the 2026-11-27 Impact rows. Full panel because the change touches executable enforcement (`lefthook.yml` pre-push, `pre_pr_sequence.py` `ci_owned_by`).
- **Pre-panel gates**: claims ledger, doc-accuracy Phase 4, self-consistency, refuting seat. Results in the ledger's Exit Gates table. The ledger path was recorded here before round 1 findings were evaluated.

## Round 1

### Agent Positions (Round 1)

| Agent | Position | Core finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | Revert Path incomplete; Kept list did not match Known non-conformances; rule 2 unqualified for a non-required scanner; 969 of 1000 lines |
| critic | Disagree-and-Commit | Scanner owner cannot block or alert; staleness gate is 13.2s, so rule 2's cost test does not retire it; ownership tests miss workflow `paths` filters |
| independent-thinker | Disagree-and-Commit | Measured-effect headline overstates n=1 at different load; "unconditional" premise false for branches with no PR; removed/kept criterion unstated |
| analyst | Accept | All counts reproduced (25, 13, 10, 10-script union); wall saving is not additive; base-ref semantics differ (refuted below) |
| security | Disagree-and-Commit | Scanner removal weakens a control the ADR frames as owned; env flag is not a trust boundary; stale workflow comment |
| high-level-advisor | Accept (conditional) | Fence origin missing; Revert Path gaps; reactive trigger names no owner |

### Round 1 Findings and Resolution

- **P1-1 (scanner owner cannot block; zero margin).** Verified: the scanner scored 80 against a minimum of 80 on 2026-11-27 (ledger row 32), the workflow has no `merge_group` trigger, and it is not in `REQUIRED_CONTEXTS`. Resolution: kept the removal on the owner ruling. The amendment now leads its Negative consequences with the zero margin, names a security finding the scanner reports (row 33), states that no other required check is verified to cover it, relabels the table column "CI Jobs That Run The Removed Passes" with the scanner row "a check, not a gate", and replaces the reactive trigger with a dated owner decision (by 2026-12-27). **Deferred with justification:** requiring the context or adding it to `workflow_failure_alert.py` `WATCHED` is a ruleset or CI-shape change; the task contract forbids changing CI shape and the ruleset belongs to the repository owner. Recorded as a trigger and a PR-body flag.
- **P1-2 (staleness gate is cheap).** Resolution: the Decision now states the criterion. A pass leaves when a CI job runs the same command on every PR; cost ranks candidates but is not the test. The 13.2s gate leaves on the owner ruling, stated as such. The ledger notes the exit-2 run still ran every generator.
- **P1-3 (ownership tests miss `paths` filters).** Resolution: code change in `e788140223`. `_owner_problems` reports a trigger carrying `paths` or `paths-ignore`; a fixture negative control proves it (ledger row 35). Trigger 2 now names `paths` filters.
- **P1-4 (measured effect overstated).** Resolution: dropped the 39 and 32 percent headline. The section now gives both raw runs, names every confound, and says the magnitude at equal load is unmeasured. Consequences say wall saved is bounded by the slowest sibling, not the 100s standalone sum.
- **P1-5 ("unconditional" premise).** Resolution: rule 6 paragraph now says `ci_owned_by` defers to merge-time CI and shows a SKIP; "unconditional" removed; "A branch with no PR gets no check" stated beside the table; the paragraph says the tests do not cover the scanner.
- **P1-6 (Revert Path incomplete).** Resolution: rewritten. Supersede, do not delete; revert the five commits or restore the two job blocks, not the whole file; names the `_NO_CALLER` entry, the 12/13 comment, both `ci_owned_by` rows, rule 2, and the five tests the Impact table omitted.
- **P1-7 (Kept list vs Known non-conformances).** Resolution: one sentence now says the Kept table matches Known non-conformances less `python-type-check` (2.73s, changed files only) plus `pre-pr-validation`.
- **P1-8 (rule 2 unqualified; size).** Resolution: rule 2 names the scanner as "a CI check, not required"; the main Consequences Negative list points to the amendment. Size is 977 of 1000 lines after round 2; a trigger requires the next amendment to move the 2026-11-26 and 2026-11-27 amendments to a successor record first.
- **P2 (Fence origin).** Added: PR #5418 (2026-08-29) and PR #6913 (2026-10-24), ledger row 34.
- **P2 (env flag).** Decision item 2 says the hook sets the flag, nothing enforces it, and it is a visibility aid, not a trust boundary.
- **P2 (stale comments).** `lefthook.yml` "Direct pre_pr.py and CI calls" and the scanner "unconditional" comment, and `plugin-scanner.yml` "also the pre-push job", fixed in `e788140223`.
- **P2 (two timing sets).** `lefthook.yml` and `SHIFT-LEFT.md` now carry the ADR's 30.3s and 56.5s.
- **P2 (stale memory).** `.serena/memories/ci/run-count-ratchets-before-the-expensive-pre-push.md` dated with a 2026-11-27 update. `.project-toolkit/metrics/hook-ownership-6734.md` is a dated 2026 measurement record and stays as history.
- **P2 refuted (analyst, base-ref semantics).** CI runs each ratchet against the merge base (`pr-validation.yml:284-295`) and `merge_tree_ratchet_check.py` against the base tip, the same two questions the local gate asked (`checks_ratchet.py:36-47`). The ADR says so; ledger row 36.
- **P2 noted, not changed (independent-thinker alternatives).** Profiling or caching `count-ratchets` still runs it locally, which the ruling rejects; a cache is folded into the glob-gate row. A scheduled `main` run of the scanner is a CI-shape change, deferred with P1-1.
- **P2 noted, pre-existing (critic).** Known non-conformances says the two 20m e2e smokes set the expensive group's cost, while `workflow-local-run` (30m) is the larger cap. The text predates this amendment; the amendment's Neutral line no longer claims which job sets the group.

## Round 2

### Agent Positions (Round 2)

| Agent | Position | Note |
|-------|----------|------|
| architect | Accept | Kept list, rule 2, and size resolved. P1: Revert Path omitted `e5f3735d62` and the doc files the commits touched |
| critic | Disagree-and-Commit | Staleness criterion and `paths` filter resolved; scanner exposure disclosed but not closed |
| independent-thinker | Accept | Measured effect, "unconditional", and criterion resolved; CPU claim (about 180s) is below the 200.8s dry-run delta |
| analyst | Accept | Row 36 refutation confirmed at `base_derived_ratchet.py:10,283,321`; ledger cell wording nit |
| security | Accept | Deferral stated honestly; spoofing the env flag skips only gates CI runs as required contexts. P2: workflow comment "owns the score" overstates |
| high-level-advisor | Accept | Fence origin, Revert Path, and trigger owner met. P2: same `e5f3735d62` omission |

### Round 2 Resolution

- **P1 (architect) and P2 (high-level-advisor), Revert Path.** Added `e5f3735d62` to the commit list, and a by-hand step to restore the comment and doc edits listed by `git show --stat 7eae0095e2 e5f3735d62 e788140223`.
- **P2 (analyst), ledger row 36.** The cell now says `--base-ref FETCH_HEAD` is the base tip and `base_derived_ratchet.py` derives the merge base from it. The ADR text was already correct.
- **P2 (security), workflow comment.** `plugin-scanner.yml:34` now says the workflow reports the score as a check, not a required gate.
- The edits are text-only fixes to the Revert Path and comments. They do not change a Decision item, so no round 3 vote ran.

### Dissent (Disagree-and-Commit)

critic: "The scanner (score 80, minimum 80) is no longer checked before push. It is a non-required check with no `merge_group` trigger. A score drop, including a security finding, can merge unread until the owner decides by 2026-12-27. I commit because the owner ruling and the no-CI-shape-change constraint are fixed inputs, and the ADR now states the exposure and sets a date. No mechanism backs that date. If a score below 80 reaches `main` first, treat it as the trigger to restore the local job or require the context."

The ADR's re-evaluation trigger already moves the owner decision earlier when a score below 80 reaches `main`.

## Strategic Review (Phase 4, high-level-advisor)

| Lens | Result | Basis |
|------|--------|-------|
| Chesterton's Fence | PASS | Origins traced to PR #5418 (2026-08-29) and PR #6913 (2026-10-24); a CI job runs each removed command |
| Path Dependence | PASS | Dated supersede, six-commit revert or named hand restore; size trigger before the next amendment |
| Core vs Context | PASS | Heavy compute is commodity and CI owns it; jobs with a named CI gap stay local |
| Second-System Effect | PASS | `ci_owned_by`, one reason code, and ownership tests with negative controls; no new framework |

**Overall Strategic Assessment**: APPROVED.

## Post-Review Text Fixes (2026-11-28, `/review` round 1 on `9182482b27`)

- **Revert Path.** The commit list named branch commits that a squash merge does not keep. The step now says to revert the pull request's squash-merge commit, and the by-hand step reads `git show --stat` on that commit. This supersedes the Round 2 edit that added `e5f3735d62` to the list.
- **Universal MUST 9.** `d31aa71e60` now carries its ISO date (2026-11-27) on both lines that cite it.
- These are text-only fixes. They do not change a Decision item, so no new vote ran.
- **Kept-jobs table after #7654 (`/review` round 2, decision-rigor).** Merging `origin/main` at `f8398e1b2d` (2026-11-27) brought #7654, which deleted the dispatch-only `plugin-cli-smoke.yml` `smoke` job and `ai-spec-review.yml`. The `hook-anchoring-e2e` and `plugin-load-e2e` row now says no workflow runs `test_cli_hook_e2e.py` and CI runs `test_plugin_load_smoke.py` only for Codex. The `security-scan` row now counts one comment, not two. Ledger rows 23, 24, and 31 were re-verified at `f8398e1b2d`. The gap grew, so keeping both jobs stands; no Decision item changed and no vote ran.
