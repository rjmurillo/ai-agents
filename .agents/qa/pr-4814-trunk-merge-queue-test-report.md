---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10023-trunk-merge-queue.json
qaCommit: c7f708d81f6fe3d3212297bc9c93802a35257106
---
# Test Report: PR #4814 - Trunk Merge Queue can complete and stops paying twice

## Scope

Worktree `/tmp/wt-trunk`, branch `fix/trunk-merge-title-exemption` against
`origin/main` merge-base `1563725cfcc6ffab271203d7b660147046891b81`. Final
implementation tip `ab65a471d907911f8e3bbf1d68234eda74df453b`.

**Diff stat (calculated independently in this session):** 6 files changed,
451 insertions(+), 8 deletions(-).

| File | Change |
|------|--------|
| `.github/workflows/semantic-pr-title-check.yml` | Trunk actor exemption, step-gated |
| `.github/workflows/ai-spec-validation.yml` | Draft skip plus `ready_for_review` trigger |
| `.trunk/trunk.yaml` | New. Queue-required status override |
| `tests/workflows/test_semantic_title_trunk_exemption.py` | New. 8 tests |
| `tests/workflows/test_spec_validation_draft_skip.py` | New. 9 tests |
| `tests/workflows/test_trunk_required_statuses.py` | New. 7 tests |

No production code changes. All three changed behaviours are CI configuration,
so runtime evidence comes from `act` and from GitHub job conclusions rather
than from unit tests alone.

## Runtime verification: the title exemption

The exemption decides whether a required status check validates or skips, so
it was executed rather than only asserted. Run through `act`
(`gh act pull_request`) against a **fork** event payload, so any dependence on
branch name or head repository would show up as a wrong answer.

| Actor | `SKIP_TITLE_CHECK` | Steps taken |
|-------|--------------------|-------------|
| `trunk-io[bot]` | `true` | notice only |
| `dependabot[bot]` | `true` | notice only |
| `someuser` | `false` | validation runs |
| `trunk-io` | `false` | validation runs |
| `trunk-io[bot]evil` | `false` | validation runs |

Matching is exact, not a prefix. The two near-miss actors are the negative
controls.

These runs also settled two mechanics that the change depends on and that are
easy to assume wrongly:

1. A step-level `if:` does read job-level `env`. There was no prior use of
   `if: env.` anywhere in `.github/workflows/`, so this had no in-repo
   precedent.
2. The folded `>-` expression spanning four lines yields the literal string
   `true`, so `== 'true'` is the correct comparison.

An earlier revision matched `startsWith(github.head_ref, 'trunk-merge/')` and
was also exercised under `act`, including `trunk-merge-evil/x` (correctly
false) and a fork claiming a `trunk-merge/` branch. That revision is not what
ships: review pointed out `trunk-io[bot]` is a real actor, which removes the
spoofing surface entirely rather than compensating for it.

**Actor provenance.** `github.actor` was read from two real runs rather than
assumed from the app name: run `31344670998` (branch
`trunk-merge/pr-4564/...-bisection`) and run `31344673874` (branch
`trunk-merge/pr-4601/...`). Both report `trunk-io[bot]`, including the
bisection case.

## Root-cause evidence, verified not inferred

| Claim | Evidence | Method |
|-------|----------|--------|
| `Validate PR title` fails on every Trunk draft | Trunk's own `Failed Required Status` table on 5 pull requests | Tally across `trunk-io[bot]` comments |
| `Validate PR` fails on Trunk drafts | draft 4805, job `93324296243`, `conclusion=failure` at step `Check QA Report Exists` | GitHub jobs API |
| Other reds are cancellations, not failures | draft 4803, job `93324287879`, `conclusion=cancelled` | GitHub jobs API |

The third row corrects an earlier claim made in this session. I initially
reported that every red except the title check was cancellation fallout. That
was true for `Validate PR` on draft 4803 and false for the same check on draft
4805, where it genuinely failed. Adversarial review surfaced it; the job
conclusion was then read directly rather than accepted from the reviewer.

## Negative controls

Every guard was verified by reintroducing the defect it exists to catch and
confirming the matching test turns red. A guard that cannot fail is not a
guard.

| Defect reintroduced | Test that caught it | Result |
|---------------------|---------------------|--------|
| Revert `semantic-pr-title-check.yml` | `test_semantic_title_trunk_exemption.py` | 6 failed, 2 passed |
| Revert `ai-spec-validation.yml` | `test_spec_validation_draft_skip.py` | 3 failed, 4 passed |
| Rename the `Run Python Tests` job | `test_every_required_status_matches_a_real_job` | red |
| Re-add `Validate PR` to the gate | `test_metadata_only_checks_are_excluded` | red |
| Add `Analyze (python)` to the gate | `test_checks_not_observed_reporting_on_a_draft_are_excluded` | red |
| Remove `ready_for_review` trigger | `test_workflow_reruns_when_a_draft_is_marked_ready` | red |
| Drop skip guard from checkout step | `test_every_step_after_the_decision_is_gated_on_the_skip` | red |

Each was restored and the suite re-run green afterwards.

Two of these tests exist only because a weaker version passed while the code
was broken:

- `test_metadata_only_checks_are_excluded` was added after
  `test_every_required_status_matches_a_real_job` passed with `Validate PR`
  configured. Name-existence proves a job exists, not that it can succeed on a
  Trunk draft.
- `test_every_step_after_the_decision_is_gated_on_the_skip` replaced an
  assertion that checked only the final failing step, which would have stayed
  green if the guard were dropped from checkout or report generation.

## Test results

| Command | Result |
|---------|--------|
| `uv run --frozen pytest tests/workflows/` | 365 passed |
| `uv run --frozen python scripts/validation/pre_pr.py` | All validations passed |
| Dash prohibition scan on all 6 changed files | 0 occurrences |
| Pre-push suite (`python-tests`, 763s) | passed |

## Coverage of the change surface

| Behaviour | Positive | Negative | Edge |
|-----------|----------|----------|------|
| Title exemption fires for Trunk | actor `trunk-io[bot]` skips | `someuser` validates | `trunk-io[bot]evil`, `trunk-io` validate |
| Bot skips preserved | all three bots asserted present | expression pinned in full | folded expression equality |
| No job-level gate | `if` absent from job | expression pinned so negation fails | branch name absent entirely |
| Draft skip | `IS_DRAFT=true` sets skip | `workflow_dispatch` leaves it empty, falls through | `ready_for_review` reruns |
| Queue gate contents | 3 names resolve to real jobs | metadata-only and unobserved checks excluded | templated names rejected |

## Known gaps

1. **No pull request has merged through the queue.** This is the only test
   that matters and it has not been run. Everything above shows the checks can
   now report correctly; none of it shows the queue completes end to end.
2. **`act` is not GitHub.** It models expression evaluation and step gating,
   which is what was tested. It does not model check-run reporting, so the
   claim that a job-level `if:` changes the reported conclusion is argued from
   the required-context deadlock of 2026-08-09, not measured here. The code
   avoids job-level `if:` on that basis and the tests pin the avoidance.
3. **Queue-gate narrowing is a deliberate coverage reduction.** Ruleset
   11104075 still gates every source pull request on all 16 contexts. Only the
   subset re-verified against the merged result changed, from 16 to 3.

## Verdict

PASS for the change as scoped, with gap 1 outstanding by construction: the
queue cannot be proven working until a pull request merges through it, and
that requires this change to land first.
