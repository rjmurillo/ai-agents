---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10033-4822-pytest-signal-shadow.json
qaCommit: 9a0f4ce702dba1e28cf2ae00c595175a5086e06b
---

# Issue 4822 phase 1 shadow pytest signal validation

## Result

PASS. The resolver, its tests, and the shadow workflow step land without
changing any existing output, consumer, or check name. The duplicate
authoritative pytest run is deliberately untouched, which is the phase 1
contract.

This revision covers commit 9a0f4ce7, which answers three review findings on
top of the original 99a4ed73. Both commits are validated together below; every
number in this report was re-measured at 9a0f4ce7.

## Evidence

- Focused tests: 83 passed in `tests/quality_gate/test_resolve_pytest_signal.py`.
- Neighbouring suites: 637 passed across `tests/workflows/` and
  `tests/quality_gate/`.
- `pre_pr.py` passed all validations.
- `ruff check`, `ruff format --check`, and `mypy` clean on both new files.
- `actionlint` exit 0. `yamllint` warning categories and counts diffed against
  the pre-change file: identical, so the edit adds no new warning.
- Taste count ratchet measured with the new files tracked: 581 violations
  against baseline 583.

## Review findings and how each is proven closed

| Finding | Fix | Test that fails without it |
| --- | --- | --- |
| Sibling FAIL masked by an executor verdict | lower tiers escalate through `worst()` | `test_an_executor_pass_does_not_mask_a_pass_through_failure` |
| Same, from a SKIPPED executor | as above | `test_an_executor_skip_does_not_mask_a_pass_through_failure` |
| Runs matched on head SHA alone | candidates must bind to the requested PR number | `test_a_colliding_sibling_run_does_not_hide_our_own_run` |
| Empty `pull_requests` opened a hole | same-repo proven against a trusted constant | `test_an_unlinked_fork_run_is_never_bound` |
| Shadow could collect zero samples silently | every run emits one sample notice, no-sample warns | `test_every_invocation_emits_exactly_one_sample_marker` |

The escalation fix carries an over-fire risk, since `pytest.yml` ships a real
`skip-tests` job with empty steps that appears alongside a green executor. If
SKIPPED escalated, every ordinary green PR would resolve SKIPPED. That inverse
is pinned by `test_a_benign_sibling_does_not_disturb_an_executor_pass` and by a
dedicated mutant below.

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
