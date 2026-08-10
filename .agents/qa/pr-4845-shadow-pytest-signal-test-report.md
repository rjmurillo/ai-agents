---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10033-4822-pytest-signal-shadow.json
qaCommit: 2360162d7e93850cce70b450ff923c810bdaeafe
---

# Issue 4822 phase 1 shadow pytest signal validation

## Result

PASS. The resolver, its tests, and the shadow workflow step land without
changing any existing output, consumer, or check name. The duplicate
authoritative pytest run is deliberately untouched, which is the phase 1
contract.

This revision covers review fix commit 2360162d7. It preserves missing local
pytest output as unknown, accepts uppercase expected SHAs, validates subprocess
timeouts, and sources the pull request number from the event payload.

## Evidence

- Focused tests: 86 passed in 0.49 seconds.
- Neighbouring suites: 637 passed across `tests/workflows/` and
  `tests/quality_gate/`.
- `ruff check` and `ruff format --check` clean on both Python files.
- `actionlint` exit 0. `yamllint` exits 0 with only pre-existing warnings.
- Security review found no exploitable issue in commit 2360162d7.
- Full `scripts/validation/pre_pr.py` passed all 50 validations.
- Taste count ratchet measured with the new files tracked: 581 violations
  against baseline 583.

## Review findings and how each is proven closed

| Finding | Fix | Test that fails without it |
| --- | --- | --- |
| Sibling FAIL masked by an executor verdict | lower tiers escalate to the worst status | `test_an_executor_pass_does_not_mask_a_pass_through_failure` |
| Same, from a SKIPPED executor | as above | `test_same_named_jobs_reduce_to_one_status[skip-hides-no-fail]` |
| Runs matched on head SHA alone | candidates must bind to the requested PR number | `test_a_colliding_sibling_run_does_not_hide_our_own_run` |
| Empty `pull_requests` opened a hole | same-repo proven against a trusted constant | `test_a_run_binds_only_when_it_provably_belongs_to_us[empty-list-fork]` |
| Shadow could collect zero samples silently | every run emits one sample notice, no-sample warns | `test_every_invocation_emits_exactly_one_sample_marker` |
| Missing local output became `SKIPPED` | pass the empty output through as unknown | `test_shadow_step_passes_missing_local_status_through` |
| Direct uppercase expected SHA became stale | normalize at the `resolve` boundary | `test_an_upper_case_expected_head_is_not_stale` |
| Invalid timeout escaped config validation | reject non-finite and non-positive values | `test_an_invalid_invocation_exits_config` |
| Shadow step depended on inherited PR wiring | source the current event PR directly | `test_shadow_step_passes_missing_local_status_through` |

The escalation fix carries an over-fire risk, since `pytest.yml` ships a real
`skip-tests` job with empty steps that appears alongside a green executor. If
SKIPPED escalated, every ordinary green PR would resolve SKIPPED. That inverse
is pinned by `test_same_named_jobs_reduce_to_one_status[benign-skipped-sibling]`
and by a dedicated mutant below.

## Discrimination check

Assertions were verified to fail when the behaviour they describe is removed.
A seventeen-mutant harness was run from outside the repository tree, restoring a
byte-identical file afterwards:

| Mutant | Outcome |
| --- | --- |
| drop push-event filter | DEAD |
| drop stale-head check | DEAD |
| best status wins instead of worst | DEAD |
| pass-through job claims PASS | DEAD |
| always read attempt 1 | DEAD |
| skipped pytest step reads PASS | DEAD |
| emit raw resolution reason | DEAD |
| emit raw agreement reason, disagree branch | DEAD |
| emit raw agreement reason, no-sample branch | DEAD |
| escalation removed, sibling FAIL masked | DEAD |
| escalation over-fires, SKIPPED not benign | DEAD |
| PR binding dropped | DEAD |
| same-repo fallback accepts anything | DEAD |
| PR number matched loosely | DEAD |
| liveness marker removed | DEAD |
| no-sample warning removed | DEAD |
| `compared` hardcoded true | DEAD |
| CONTROL: comment-only edit | SURVIVED as required |

The surviving control proves the suite is not failing on unrelated edits.

Building this harness found a real gap rather than confirming the suite. The
mutant emitting a raw agreement reason was reported as not applying once the
liveness work gave its target two call sites. Splitting it per branch showed the
sanitizer on the no-sample warning was unobserved, and the mutant against that
branch survived. `test_the_no_sample_warning_sanitizes_the_reason_it_is_handed`
was added and both branches now die.

## Validation against live GitHub data

The parser was run over captured API responses so the job shapes are observed
rather than assumed.

| Run | Shape | Resolved |
| --- | --- | --- |
| 31360441685 | run success, both jobs success, `Run pytest` skipped | SKIPPED |
| 31355229018 | executor green, pass-through skipped with empty steps | PASS |
| 31362376502 | both jobs cancelled, empty step lists | CANCELLED |
| 31361938848 | executor in progress, null conclusions | PENDING |
| 31360447277 | startup failure, no jobs at all | UNKNOWN |

Run 31360441685 is the case that motivates step-name classification. GitHub
reports the run and both same-named jobs as `success` while the suite never
executed, so a resolver reading either conclusion would report PASS for an
untested commit. That payload is pinned as a regression test.

An end-to-end run against live PR 4819 returned `shadow_pytest_status=PASS`
with `shadow_pytest_agreement=AGREE` and exit 0. Re-run at 9a0f4ce7 against open
PR 4833 it returned `shadow_pytest_status=PENDING` with
`shadow_pytest_compared=true`, one sample notice and one disagreement warning,
exit 0.

PR binding was proven on a real payload rather than a synthetic one. The run
captured for PR 4833 binds when 4833 is requested (1 bound, 0 rejected) and is
rejected when 4834 is requested (0 bound, 1 rejected).

The empty `pull_requests` array is normal, not anomalous. Live reads on
2026-08-10 show open PRs 4832, 4833, 4834 and 4817 each carrying their own
number, while every run of merged PR 4819 carries an empty list. Treating the
empty list as a failure would therefore break the resolver on closed PRs, which
is why the same-repo fallback exists.

## Revalidation at 0e88151e

Commit 0e88151e deletes code, not behaviour: the resolver falls from 729 to 494
lines and the tests from 988 to 491, so both clear the 500-line gate that was
blocking the build. Nothing above changed, and four independent checks say so.

A differential run loaded the pre-change module and the post-change module side
by side and drove both through 24 API scenarios (stale head, no run, pass,
skipped, the green-but-unrun payload, sibling failure, benign sibling,
cancelled, pending, unrecognised conclusion, unbound run, fork, empty links,
push run, third attempt, and every unreadable or malformed response) crossed
with 5 local statuses. It compared the status, the reason, stdout, stderr, and
every emitted output key. Zero differences. A second differential drove `main`
over 6 argument vectors including every rejected invocation: identical exit
codes and streams. `--help` is byte-identical, so the command line surface did
not move either.

The suite still reports 83 cases. Test bodies that differed only in data became
parametrize tables, which holds the case count while the line count falls: run
binding 10 cases, job tier aggregation 15, unusable API data 7, compare 5,
invalid invocations 5. The 31360441685 payload is still pinned verbatim.

A 20-mutant battery run from a clean tree covers the whole contract: stale head,
push filter, head SHA, PR binding, fork rejection, run and attempt selection,
the skipped pytest step, pass-through tiering, incomplete jobs, tier precedence,
sibling escalation and its benign inverse, unrecognised conclusions, unbound
runs, the job-name filter, sanitation, config exit, and both unreadable-payload
guards. All 20 DEAD, none survived.

Re-measured: 83 focused tests pass, 637 across `tests/quality_gate/` and
`tests/workflows/`, `pre_pr.py` passes, `ruff check`, `ruff format --check` and
`mypy` clean on both files, and taste-lints reports 0 errors where it previously
reported 2 file-size errors.

Two internal surfaces did change, neither observable to a caller: `__all__` was
deleted, so the module no longer curates a star-import list, and `gh_json` now
returns the payload or None instead of a (bool, object) pair, which moved the
non-Mapping guard out of `parse_runs` into the one place that reads the body.
Cohesion remains 1.0 because that score is a function of file length and
definition count alone, so only splitting the module can raise it, and the
file budget for this change forbids a sixth file.

## Revalidation at 34cf0678

The `skip-hides-no-fail` case now gives the executor a valid `success`
conclusion and a skipped pytest step. It therefore exercises the intended
successful executor plus failing sibling path. The 83 focused tests pass, Ruff
passes, and taste-lints reports no blocking finding.

## Accepted residual risk

With an empty `pull_requests` array, two same-repo pull requests sharing one
head commit are indistinguishable. The exposure is bounded because both ran the
identical tree and the caller has already proven the SHA is the live head of the
requested PR. A fork cannot reach this path: the fallback compares
`head_repository.full_name` against the already validated repository constant,
which a fork by definition cannot match. That comparison never ingests the
value, so no fork-controlled text is emitted, stored, or used to build a
request.

## Not verified here

The shadow step has not executed under a real `GITHUB_TOKEN`. Local runs used a
personal token, so the sufficiency of `actions: read` for the workflow token is
unproven until the step runs in CI. That exposure is bounded: the step is
`continue-on-error`, every resolution outcome exits 0, and no consumer reads
its outputs, so a token failure surfaces as UNKNOWN and changes no verdict.
Measuring that, and the PENDING versus PASS disagreement rate created by the 45
minute pytest.yml budget against the 10 minute run-tests budget, is the purpose
of phase 1.
