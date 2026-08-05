# Retrospective: Truncated-window reductions in the fleet PR queue

## Session Info

- **Date**: 2026-08-04
- **Agents**: Copilot CLI (Opus 5) orchestrator, three background fix agents (4512, 4517, 4554)
- **Task Type**: Bug
- **Outcome**: Partial

## Phase 0: Data Gathering

4-Step Debrief.

- **Observe**: Draining a queue of open PRs. Twenty showed a red aggregate. The plan of
  record was to apply the #4553 remedy (merge main, push again) across the whole set.
- **Respond**: Queried the queue, then queried the failing check names before acting.
- **Analyze**: The dominant failure was `Validate PR` on 11 of 14, not the ruff ratchet.
  Root cause was #4518: a `git fetch --depth=1` severs history so `git merge-tree`
  cannot find a merge base.
- **Apply**: Fixed #4518 at the source instead of re-pushing 14 branches.

Execution Trace.

| # | Action | Result |
|---|---|---|
| 1 | Read #4426 thread, found the early-return claim | Claim sound |
| 2 | Built a worktree, found a stranded unpushed commit | Fix already existed |
| 3 | Ran a four-cell control on the guard | Pre-fix vacuous, post-fix fails |
| 4 | Batched one aliased GraphQL query over 20 PRs | 20 answers, one call |
| 5 | Filtered `contexts(last:60)` for failures | Returned nothing for 3 PRs |
| 6 | Noticed the filter contradicted the server rollup | Filter distrusted |
| 7 | Re-queried with `totalCount` | 131 contexts; window dropped the failure |
| 8 | Validated `gh pr checks` against the known answer | Found `Validate PR` |
| 9 | Reproduced #4518's control matrix locally | All three cells matched |
| 10 | Fixed workflow, error message, and added two guards | 66 tests pass |

Outcome Classification.

- **Glad**: The contradiction between my filter and the server rollup was caught, not
  published. The #4518 fix removes a gate failure from 11 PRs at once.
- **Sad**: The `--depth=1` fetch had to be reproduced before I trusted a well-written
  issue. That is correct, but it means issue quality does not buy trust.
- **Mad**: I reset a branch and would have destroyed a colleague agent's unpushed commit
  had I not listed non-base commits first.

## Phase 1: Insights Generated

Five Whys, on "my failure filter reported no failing checks for PR 4402".

1. Why did the filter report nothing? It scanned `contexts(last:60)`.
2. Why was that not enough? The head SHA carries 131 contexts.
3. Why 131? `pytest.yml` runs on both `push` and `pull_request`, so each job appears
   twice, and the repository has roughly 65 jobs.
4. Why did I choose 60? I picked a window that felt generous without measuring the
   population it had to cover.
5. Why did I not measure? The query returned a well-formed answer, and a well-formed
   answer reads as a correct one.

Root cause: **a reduction was sized by intuition rather than against `totalCount`, and
its output carried no signal that it had truncated.**

Patterns and Shifts.

This is the third instance of one shape in this session, and they were not recognized as
the same shape until now.

| Instance | Reduction | Why it under-reported |
|---|---|---|
| Latest run per check name | Keeps one row per name | Two triggers emit two rows; neither supersedes |
| `contexts(last:60)` | Keeps 60 of 131 | The failing row fell outside the window |
| ruff B018 probe | Single negative control | The control could not fire, so silence proved nothing |

All three produced a plausible answer from an incomplete view. None announced the loss.

## Failure Mode Classification

Per `.agents/governance/FAILURE-MODES.md`, this incident maps to one existing class. No new
class is required.

### Primary: FM-10 Silent Defaults and Guard-Clause Suppression

FM-10's unifying property is that the call site has no way to know the operation did not do
what its name claims. FM-10's catalogued shapes are all code-level: `except: pass`,
`value or default`, a parser falling through to `{}`. This incident is the same property
expressed in a query reduction rather than in a guard clause.

`contexts(last:60)` against a head SHA carrying 131 contexts returned a well-formed, empty
failure list. Nothing in the response distinguished "no failures" from "the failing row fell
outside the window". All three instances in the Patterns table above share that shape: each
produced a plausible answer from an incomplete view, and none announced the loss.

The FM-10 enforcement pattern generalizes to match: surface the suppression. For a reduction,
that means requesting `totalCount` alongside the window and comparing the two before reading
the result, so a truncation announces itself the way a logged exception would.

Not FM-9. FM-9 requires claiming parity with a canonical source without quoting it. The window
size here was chosen without consulting any contract at all, so there was no contract to
misquote.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Query failing check names before broadcasting a remedy | 11 of 14 were `Validate PR`, not the ratchet | 9 | 75% |
| Treat a server-computed aggregate as authoritative over a local reduction | Rollup FAILURE beat my empty filter | 9 | 75% |
| Validate an instrument against a known answer before trusting it | `gh pr checks` found `Validate PR` on 4402 | 8 | 75% |
| Reproduce an issue's control matrix before acting on it | All three cells matched, fix justified | 7 | 75% |
| List non-base commits before a reset | Found a stranded commit that a reset would have destroyed | 9 | 75% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| `contexts(last:60)` failure filter | Truncated window | Window sized by intuition, not `totalCount` | Request `totalCount` and compare before reducing | 75% |
| Planning a 14-PR remedy broadcast from rollup state alone | Unverified generalization | Aggregate state does not name the failing check | Read failing check names first | 75% |
| Reading push success from validator log text | Wrong instrument | "All validations passed" precedes the network push | Compare `ls-remote` SHA to `rev-parse HEAD` | 75% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Reporting "no failing checks" for three PRs the server called red | Noticed the contradiction and distrusted my own filter | A local reduction that disagrees with the server is wrong until proven otherwise |
| `git reset --hard` over an unpushed fix from another agent | Listed `--no-merges base..HEAD --not origin/main` first | A branch may carry work no one announced |
| Adding a behind-base test that could never catch the regression | Ran it against the pre-fix tree and saw it pass | A guard that controls its own inputs cannot observe the input it guards |

## Phase 3: Decisions

### Action Classification

| Action | Class | Detail |
|---|---|---|
| Fix #4518 at the workflow, not per branch | Add | Full-depth fetch for the merge-tree step only |
| Name the cause on rc 128 | Add | Error text points at the fetch, not the script |
| Assert the workflow's fetch depth | Add | The behaviour test cannot see a workflow revert |
| Keep `--depth=1` on the two count ratchets | Keep | They read one baseline object and never walk history |
| Sizing a result window by intuition | Drop | Compare to `totalCount` or use a paginating client |
| Broadcasting a remedy from aggregate state | Modify | Read failing check names first |

### SMART Validation

- Specific: each learning names an instrument and the comparison that validates it.
- Measurable: `totalCount` versus window size; `ls-remote` SHA versus `rev-parse HEAD`.
- Achievable: all are single commands already in use.
- Relevant: each maps to a wrong conclusion reached this session.
- Time-bound: applies at the moment the instrument is chosen, before its output is read.

### Action Sequence

1. Fix #4518 (done: workflow, message, two guards, 66 tests pass).
2. Write this retrospective (unblocks the push gate, which is working as designed).
3. Push #4518 and open the PR.
4. Re-measure the queue after #4518 lands, because 11 red checks should clear.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: Ask the server for statusCheckRollup instead of reducing check rows locally
- **Atomicity Score**: 75%
- **Evidence**: PR 4402 rollup FAILURE while a `last:60` filter returned no failing rows
- **Skill Operation**: UPDATE
- **Target Skill ID**: decision-measure-pr-checks-by-head-sha

### Learning 2

- **Statement**: Reduce a check-status window only after comparing its size to totalCount
- **Atomicity Score**: 75%
- **Evidence**: 131 contexts on one head SHA; a 60-row window dropped the failure
- **Skill Operation**: UPDATE
- **Target Skill ID**: decision-measure-pr-checks-by-head-sha

### Learning 3

- **Statement**: Prove a detector fails on a known-bad input before trusting its silence
- **Atomicity Score**: 75%
- **Evidence**: a ruff B018 probe passed on a control that could not fire
- **Skill Operation**: ADD

### Learning 4

- **Statement**: List commits absent from the base before resetting a branch
- **Atomicity Score**: 75%
- **Evidence**: commit 79314576b was unpushed on fix/gate-enforcement-clean
- **Skill Operation**: ADD

### Learning 5

- **Statement**: Verify a push landed by comparing git ls-remote SHA to git rev-parse HEAD
- **Atomicity Score**: 75%
- **Evidence**: push4426 printed "All validations passed" and then failed to push
- **Skill Operation**: ADD

## Skillbook Updates

### ADD

```json
{
  "skill_id": "measurement-window-vs-population",
  "statement": "Reduce a check-status window only after comparing its size to totalCount",
  "context": "Before filtering any paginated GraphQL result set",
  "evidence": "PR 4402: 131 contexts, last:60 window, failing row dropped",
  "atomicity": 75
}
```

```json
{
  "skill_id": "detector-negative-control",
  "statement": "Prove a detector fails on a known-bad input before trusting its silence",
  "context": "Before reporting that a scan or lint found nothing",
  "evidence": "ruff B018 probe passed on a binary-op control B018 never flags",
  "atomicity": 75
}
```

```json
{
  "skill_id": "git-reset-preflight",
  "statement": "List commits absent from the base before resetting a branch",
  "context": "Before git reset --hard on a branch another agent may have touched",
  "evidence": "commit 79314576b was unpushed and would have been destroyed",
  "atomicity": 75
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| decision-measure-pr-checks-by-head-sha | Reduce to latest run per check name | Read the server's statusCheckRollup | Two triggers emit two rows under one required name; neither supersedes |
| decision-measure-pr-checks-by-head-sha | No window guidance | Compare window size to totalCount | A 60-row window silently dropped the failing row of 131 |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| decision-measure-pr-checks-by-head-sha | harmful | Prescribed reduction returned the wrong verdict on a two-trigger PR | 9 |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| (none) | | |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| measurement-window-vs-population | decision-measure-pr-checks-by-head-sha | High | Update the existing memory, add the window rule as a new clause |
| detector-negative-control | testing rigor: positive, negative, edge | Medium | Add; the existing rule governs authored tests, not ad hoc probes |
| git-reset-preflight | none found | Low | Add |
