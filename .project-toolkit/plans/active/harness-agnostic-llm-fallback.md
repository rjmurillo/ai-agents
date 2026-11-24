# Execution Plan: Harness-Agnostic Model Fallback for Comment Actionability

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress (M1-T1 to M1-T10 and M1-T13 to M1-T15 built; labeling method open) |
| **Created** | 2026-11-23 |
| **Owner** | Richard Murillo (plan drafted by Claude) |
| **Complexity** | Medium |
| **Spec** | `.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md` |
| **Base** | `84c395f822`, branch `t3/f1903a51` |

## Objectives

- [ ] M1: eval report and decision record committed (spec AC 8)
- [ ] Decide: kill path (M-K) or build path (G1, M2, M3, M4)
- [ ] Build path only: AC 1 to 7 each map to a passing test
- [ ] Build path only: steady-state CI run clears kill criterion 5

## Shape

Eval before build. M1 changes no production code. Its exit is a decision against the five kill criteria.
If any criterion fires, the only next milestone is M-K (delete the fallback).
Two owner gates: G0 (is a CI secret acceptable, spec Open question 5) feeds kill criterion 4 inside M1.
G1 (where the transport seam lives, an architecture call) gates the build path.

## Milestones

### M1: Eval (measurement only)

Exit criteria:

1. Band measurement committed first, on its own, split into thread openers and replies, with truncation loss and the PR `updatedAt` window stated. If the band share is under 5 percent, kill criterion 1 fires and M1-T6 onward do not start.
2. Rubric, 200-item JSONL corpus with diff hunks, frozen prompt and model, and runner committed under `evals/comment-actionability/`. Runner code has tests under `tests/`.
3. Report states per-arm accuracy, precision, recall; arm C p50 and p95 latency on an HTTP transport; paired bootstrap 95 percent CI on C minus the better of A and B over the 60 held-out band items; minimum detectable gap; labeler agreement on 50 double-labeled items.
4. Decision record marks each kill criterion fired, cleared, inconclusive, or projected, with evidence. Criterion 2 cites the pass bar. Criterion 4 cites the G0 answer. Criterion 5 is projected as a run count to steady state.
5. `git diff --stat 84c395f822 -- scripts/llm_classification scripts/update_reviewer_signal_stats.py scripts/github_core` is empty.

Unblocks: M-K or G1. Gate before: none.

### M-K (conditional): delete the fallback

Trigger: any kill criterion fires in M1 (at M1-T5 or M1-T20), or criterion 5 fires in M4.

Exit criteria: no reference to `llm_classification` remains (search command and result recorded); heuristic stats table equals a golden file captured before deletion; existing tests pass; any workflow secret, env line, or cache step added by M4 is gone.
Rollback: `git revert` of the deletion commit.

### G0: owner decision on the CI secret (spec Open question 5)

Asked at M1 start. A decline with no secret-free CI transport fires kill criterion 4.

### G1: owner decision on the transport seam (Ask First, architecture)

Options from spec Open question 1: A promote `scripts/eval/_providers.py` to a package with an ADR; B `sys.path` import; C small stdlib transport inside `llm_classification`.
Opens only if M1 clears every criterion. This plan does not decide it.

### M2: transport seam

Exit criteria (option A): ADR accepted through `adr-review` with a debate log; stdlib OpenAI-compatible and Anthropic clients exist and are tested; `scripts/eval` repointed with eval tests unchanged; package imports with `anthropic` and `openai` blocked.
Ships alone as a refactor: nothing in production changes. Rollback: `git revert` of the refactor commit. Gate before: G1.

### M3: contract, cache, counters (default off)

Exit criteria: tests for spec AC 1 to 7 pass; old-contract tests in `tests/llm_classification/` updated; `_write_step_summary` (`update_reviewer_signal_stats.py:575`) prints the counters; unconfigured run writes a stats table byte-equal to the pre-change run.
Rollback: `git revert`; ships default off, so production output is unchanged. Gate before: G1, plus M2 under option A.

### M4: CI rollout

Exit criteria: PR merged with secret and env lines, cache step, SHA-pinned actions, and a `/review` marker; one cold and one warm `workflow_dispatch` run read; steady-state check of kill criterion 5 recorded.
Rollback: remove the env lines; the heuristic stands. Gate before: M3 and G0 (accepted).

## Tasks

Sizes are complexity, not time: S one concern, M several concerns or a new module, L cross-cutting.

### M1

| ID | Task | Done when | Size | Deps |
|---|---|---|---|---|
| M1-T1 | Ask the owner G0 (CI secret) | Question sent; answer slot in decision record | S | none |
| M1-T2 | Measure the heuristic band | Script under `scripts/eval/` reuses `get_comments_by_reviewer` (`update_reviewer_signal_stats.py:179`) and `get_actionability_score` (`:250`); prints band count and share, share at exactly 0.5 with no matched reason, split by thread position; tests with mocked `gh` | M | none |
| M1-T3 | Count fetch truncation | Same script counts PRs at 100 threads and threads at 50 comments (`scripts/github_core/api.py:1313-1317`); reports them; test with a truncated fixture | S | M1-T2 |
| M1-T4 | Commit the band result alone | Result file with SHA, date, window semantics, and loss counts; exit criterion 5 diff guard empty | S | M1-T3 |
| M1-T5 | Apply kill criterion 1 | Share recorded; under 5 percent triggers M-K | S | M1-T4 |
| M1-T6 | Write the labeling rubric | Defines the unit (comment node, with thread position), actionable vs not, edge examples; states whether thread `isOutdated` is shown | M | M1-T5 |
| M1-T7 | Build the stratified sampler | Seeded; 200 rows, 100 in band and 100 outside, every signal-table reviewer present; 40 band rows marked dev | M | M1-T5 |
| M1-T8 | Fetch diff hunks for sampled rows | Each row carries path and hunk; rows with no hunk are flagged, not dropped | M | M1-T7 |
| M1-T9 | Scan the corpus for secrets | `scripts/redact_secrets.py` reports no matches | S | M1-T8 |
| M1-T10 | Generate the blinded labeling sheet | Shows comment, path, hunk; omits replies, scores, arm outputs; a test asserts both | S | M1-T8 |
| M1-T11 | Label 200 items | Labeler named; every row labeled per rubric. Human effort: 200 judgments | M | M1-T6, M1-T9, M1-T10 |
| M1-T12 | Double-label 50 items | Second labeler named; agreement rate recorded | M | M1-T11 |
| M1-T13 | Implement arms A and B | Unit tests at the 0.5 boundary | S | M1-T5 |
| M1-T14 | Implement arm C | Heuristic, then a `scripts/eval` HTTP provider cell, then the 0.7 apply rule; tests with a fake provider | M | M1-T5 |
| M1-T15 | Implement metrics, latency, bootstrap CI, and minimum detectable gap | Seeded, reproducible tests on fixed inputs | M | M1-T13, M1-T14 |
| M1-T16 | Tune and freeze the prompt on the dev split | Prompt, provider, model committed before held-out scoring | S | M1-T11, M1-T14 |
| M1-T17 | Run the eval on held-out items | Results committed with provider, model, SHA, date | M | M1-T12, M1-T15, M1-T16 |
| M1-T18 | Rank reviewers under A and C on the full set | Arm C over band comments within the 200-call cap; ranking diff recorded for criterion 3 | M | M1-T17 |
| M1-T19 | Project steady state for criterion 5 | Run count from `band_total`, p50, caps | S | M1-T17 |
| M1-T20 | Write the decision record | Five criteria marked with evidence; inconclusive branch applied if the CI straddles 0 | M | M1-T18, M1-T19, M1-T1 |

`eval-prompt-change.py` is not reused: it scores before and after prompt pass rates and cannot model the 0.7 apply rule or three arms.

### M-K

| ID | Task | Done when | Size | Deps |
|---|---|---|---|---|
| MK-T1 | Capture the heuristic golden output | Stats table for a fixed input saved before any change | S | M1-T5 or M1-T20 (whichever fires) |
| MK-T2 | Record the pre-removal reference search | Command and hits logged | S | MK-T1 |
| MK-T3 | Remove the wiring | Import at `:53`, setup at `:750-765`, `llm_classifier` params at `:253`, `:417`, `:441`, fallback block at `:329-351` | M | MK-T2 |
| MK-T4 | Delete the module and its tests | `scripts/llm_classification/` and `tests/llm_classification/` gone | S | MK-T3 |
| MK-T5 | Remove any M4 workflow additions | Secret, env lines, cache step gone; `/review` marker if the workflow changed | S | MK-T3 |
| MK-T6 | Prove the heuristic unchanged and references gone | Equals MK-T1 golden; suite passes; post-removal search has zero hits | S | MK-T4, MK-T5 |

### G1

| ID | Task | Done when | Size | Deps |
|---|---|---|---|---|
| G1-T1 | Present the transport-seam decision brief | Options A, B, C sent; choice logged in Decision Log | S | M1-T20 (all cleared) |

### M2 (option A; see note for B and C)

| ID | Task | Done when | Size | Deps |
|---|---|---|---|---|
| M2-T1 | Draft the ADR | `adr-generator` output exists | M | G1-T1 |
| M2-T2 | Review the ADR | `adr-review` debate log; consensus | M | M2-T1 |
| M2-T3 | Snapshot the eval test baseline | `scripts/eval` tests green, result saved | S | G1-T1 |
| M2-T4 | Promote the provider seam to a package | Sibling imports at `_providers.py:59-67` resolved inside the package | L | M2-T2, M2-T3 |
| M2-T5 | Repoint `scripts/eval` callers | Search shows no old-path import | S | M2-T4 |
| M2-T6 | Build the stdlib OpenAI-compatible client | `urllib` only; timeout and HTTP error mapping | M | M2-T4 |
| M2-T7 | Expose the stdlib Anthropic client | Reuses `scripts/eval/_anthropic_api.py` path; no SDK import | S | M2-T4 |
| M2-T8 | Test both clients | Fake server covers success, 5xx, 401, timeout, malformed body | M | M2-T6, M2-T7 |
| M2-T9 | Add the import-blocked test | Package imports with `anthropic` and `openai` blocked | S | M2-T6, M2-T7 |
| M2-T10 | Confirm eval tests unchanged | Same tests pass, none edited | S | M2-T5 |

Under option B: drop M2-T1, T2, T4, T5; add one task to wire the `sys.path` import. The `openai` SDK import in the existing cell then conflicts with AC 1, so M2-T6 stays. Under option C: M2 collapses to M2-T6 to T9 as modules inside `scripts/llm_classification`.

### M3

| ID | Task | Done when | Size | Deps |
|---|---|---|---|---|
| M3-T1 | Settle spec Open question 2 (summary granularity) | Answer logged | S | G1-T1 |
| M3-T2 | Define the `Transport` protocol and a fake | Fake conforms; typed test | S | G1-T1 |
| M3-T3 | Add the config surface | `PROVIDER`, `MAX_CALLS`, `BUDGET_SECONDS`, `TIMEOUT`; new `ENABLED` default; Haiku default removed; tests per variable | M | G1-T1 |
| M3-T4 | Parse replies strictly | Non-bool `is_actionable` returns `None`; one test per bad shape | S | M3-T2 |
| M3-T5 | Add truncated thread replies to the input | Limits tested at the boundary | S | M3-T2 |
| M3-T6 | Enforce budgets | Timeout, one transient retry, call cap, wall budget; one test per limit | M | M3-T2, M3-T3 |
| M3-T7 | Select the provider | `LLM_FALLBACK_PROVIDER` wins; HTTP-only auto-detect; tests | M | M3-T2, M3-T3 |
| M3-T8 | Add the cross-run cache | Key per spec; hit, miss, version-change, corrupt-file tests | M | M3-T4, M3-T5, M3-T7 |
| M3-T9 | Replace the SDK call in `classifier.py` | No `anthropic` import; calls `Transport`; test conformance of real clients | M | M3-T4, M2-T9 (A) or M2 option tasks (B, C) |
| M3-T10 | Update old-contract tests | `tests/llm_classification/` asserts the new contract | M | M3-T9 |
| M3-T11 | Wire the fallback into scoring | Runs only when a transport resolves; three call sites in `update_reviewer_signal_stats.py` | L | M3-T6, M3-T8, M3-T9 |
| M3-T12 | Implement the secret-presence truth table | All nine spec cases: status, exit 0, 2, 3, or 4, annotation level; stats written first in every case; empty env value treated as absent; empty `OPENAI_BASE_URL` never selects an endpoint; one `main(argv)` test per case with inherited model keys stripped; a planted key value never appears in output | L | M3-T11 |
| M3-T13 | Print counters in the step summary | Counters and the unconfigured line present; test | S | M3-T11, M3-T1 |
| M3-T14 | Prove default off leaves stats unchanged | Unconfigured stats table byte-equal to baseline | S | M3-T11 |
| M3-T15 | Add the AC 2 literal scan and AC 7 CLI tests | Scan fails on a `claude-`, `gpt-`, `gemini-` default; CLI cells checked for tools-off argv and stripped env | S | M3-T9 |
| M3-T16 | Map AC 1 to 7 to tests | Each AC names a passing test | S | M3-T10, M3-T12, M3-T13, M3-T14, M3-T15 |

M3-T1 to T8 build against the fake transport, so they run alongside M2.

### M4

| ID | Task | Done when | Size | Deps |
|---|---|---|---|---|
| M4-T1 | Map the existing `agent-claude` key into the stats step | `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` added to the step env at `update-reviewer-stats.yml:77`; no `LLM_FALLBACK_PROVIDER` set, so a fork lands in case 2, not case 4; a parsed-YAML test pins both | S | G0 accepted, M3-T16 |
| M4-T2 | Add the cross-run cache step | Per-run key, prefix restore, SHA-pinned | S | M4-T1 |
| M4-T3 | Run pre-PR validation | `pre_pr.py` passes | S | M4-T2 |
| M4-T4 | Add the `/review` marker commit | Marker on the tip before push | S | M4-T3 |
| M4-T5 | Open and merge the PR | Owner approves and merges | S | M4-T4 |
| M4-T6 | Run cold, then warm, by `workflow_dispatch` | Both summaries read; counters present | S | M4-T5 |
| M4-T7 | Check kill criterion 5 at steady state | After the projected run count, or one backfill run: `fallback_capped` at or under 10 percent of `band_total`, or recorded as fired | S | M4-T6 |

## Dependency graph

```text
M1-T1 (G0 ask) ------------------------------------------------------+
M1-T2 -> T3 -> T4 -> T5 -+-> T6 ----------------------+               |
                         +-> T7 -> T8 -+-> T9 --------+-> T11 -> T12 -+
                         |             +-> T10 -------+       |       |
                         +-> T13 -+-> T15 ---------------+    v       |
                         +-> T14 -+-> T16 (needs T11) ---+-> T17 -> T18, T19 -> T20
                                                                              |
     kill at T5 or T20 -> MK-T1 -> T2 -> T3 -> T4, T5 -> T6                   |
     all cleared at T20 -> G1-T1 -> M2 (A) ----------------+                   |
                                \-> M3-T1..T8 (fake) ------+-> M3-T9.. -> M4 (needs G0 accepted)
```

Parallel tracks after M1-T5: labeling (T6 to T12) and runner (T13 to T15).

## Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Model-made labels grade a model arm with a model's judgment | High | Arm C scores inflated when labeler and arm C share a vendor or prompt style | Labeling method is open (owner, 2026-11-24). If a council labels: council members exclude arm C's vendor, labels come from majority vote, council never sees arm outputs, and a human spot-checks a sample. Decide before M1-T11 |
| R2 | The fetch drops rows: no `pageInfo` on `reviewThreads(first: 100)` and `comments(first: 50)`, PR `updatedAt` window | High | Band share and corpus skew toward small PRs | M1-T3 counts and reports truncation; result states window semantics; fixing the fetch is deferred, not hidden |
| R3 | Replies are scored as comments, so "thanks, fixed" rows enter the band | High | Kill criterion 1 measured on the wrong unit | Split band share by thread position; rubric fixes the unit to match production |
| R4 | 60 held-out band items cannot detect a 10-point gain | High | Kill criterion 2 fires on noise | Minimum detectable gap computed first; inconclusive branch adds 100 band items once |
| R5 | Prompt overfits the labeled set | Medium | Inflated arm C | 40-item dev split; prompt and model frozen and committed before held-out scoring |
| R6 | Arm C on a laptop CLI differs from CI | High | Accuracy and p95 do not transfer | Arm C runs on an HTTP cell with the CI candidate model; CLI numbers count for accuracy only |
| R7 | Steady state needs many daily runs when `band_total` exceeds the call cap | Medium | Criterion 5 unjudgeable at M4 | M1-T19 projects run count; one backfill run with raised caps allowed |
| R8 | Promoting `_providers.py` breaks eval tests | Medium | M2 stalls | M2-T3 baseline; M2-T10 proves tests unchanged; option B or C as fallback |
| R9 | Workflow edit blocked at push | High | M4 push refused | M4-T4 marker commit after the last change |
| R10 | Prompt injection in comment text | Low | One wrong label | Tools off, typed three-field parse, eval measures label quality |

## Deferred items

- Fixing the fetch truncation and the PR `updatedAt` window in `scripts/github_core/api.py`. It also affects the heuristic today. Separate change, owner's call.
- Fixing the heuristic's 0.5 tie-break. Arm B measures it.
- Scoring only thread openers instead of every node. M1 reports the split; changing production is separate.
- Cursor, Muse, and Hermes transports. Each needs a tool-less probe first.
- The other direct model calls in the spec recon table.
- Spec Open questions 3 (harness auto-detect) and 4 (nested-session hook refire). CLI transports stay opt-in until answered.
- `.project-toolkit/specs/STATUS.md` refresh.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-11-23 | Eval before build; M1 changes no production code | Owner chose spec option B on condition the fallback proves its value | Build first, then measure |
| 2026-11-23 | New eval runner instead of `eval-prompt-change.py` | That runner cannot model the 0.7 apply rule or three arms | Extend `eval-prompt-change.py` |
| 2026-11-23 | Spec amended: eval unit, diff hunks, dev split, inconclusive branch, steady-state criterion 5 | Pre-mortem found the original eval measured the wrong unit and could not reach a verdict | Keep the original eval |
| 2026-11-23 | G0 (CI secret) moved before G1 | Kill criterion 4 needs the answer; asking after M3 risks wasted build work | Ask at M4 |
| 2026-11-24 | G0 answered: a CI secret is acceptable if the eval passes | Owner decision; kill criterion 4 cleared conditionally | No secret (fires criterion 4) |
| 2026-11-24 | Labels will not be hand-made; owner suggests an LLM council; method decided later | Owner decision | Owner labels 200 by hand |
| 2026-11-24 | Secrets are optional; absence is never an error and never silent; a present key that fails is always an error | Owner asked for no false positives and no false negatives. The job already runs under `agent-claude`, which holds `ANTHROPIC_API_KEY` (names listed 2026-11-24) | Fail when the key is absent (false alarms on forks); stay silent (today's false negative) |
| 2026-11-24 | Build only M1-T2 to M1-T5 now | Owner decision; band share alone could kill the effort | Stop at plan; build all of M1 |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-11-23 | Created plan from spec | Claude (milestone-planner, task-decomposer) |
| 2026-11-23 | Revised after pre-mortem (7 risks) and critic (19 defects, verdict REVISE) | Claude (analyst, critic) |
| 2026-11-24 | M1-T2, T3 done: `scripts/eval/measure_actionability_band.py`, 18 tests | Claude |
| 2026-11-24 | M1-T4, T5 done: 819 of 4,647 comments in band (17.6 percent) across 837 PRs, measured 2026-11-24 at `951c9dba9c`. Openers 800 of 4,034, replies 19 of 613. 0 truncated PRs, 0 truncated threads. Kill criterion 1 cleared. | Claude |
| 2026-11-24 | M1-T6 to T10, T13 to T15 built: rubric, runbook, sampler, hunk fetch, secret scan, blinded sheet, merge-labels, predict, score. 629 tests at `2915538c12`. Real-data `sample` exits 0: 200 rows, 0 blocking, 56 SHA rows reported, 39 public bot ids. | Claude (implementer) |
| 2026-11-24 | Review round 1 at `b990cd6470`: CRITICAL_FAIL (JSONL broke on U+2028; kill criterion 1 compared a rounded share). Fixed in 10 commits. Round 2 correctness axis only, at `2915538c12`: all 10 fixed, WARN on one finding left as intended behavior (breaker exits 3 on a trailing streak; pinned by `test_the_breaker_fires_even_when_the_failure_rate_is_low`). No review marker: the other axes were not rerun. | Claude |
| 2026-11-24 | Open owner decisions from review: verdict rule can fail on noise at n=60 (detectable gap 0.114 to 0.198 vs 0.10 bar); labeler agreement floor; 64-hex handling; 0.7 gate is commenter-influenceable before any production wiring; measure kill criterion 3 early. | Claude |

## Blockers

- Labeling method (M1-T11, M1-T12) waits on the owner. M1-T6 to M1-T10 and M1-T13 to M1-T15 are not blocked.
- G1 (transport seam) opens only after M1-T20.

## Related

- Spec: `.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md`
- Issue: none filed
- PR: none
- ADR: needed only if G1 picks option A
