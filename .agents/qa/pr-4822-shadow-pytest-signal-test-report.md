---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10033-4822-pytest-signal-shadow.json
qaCommit: 99a4ed7305830ac74a58532d7eab35f38dd749b5
---

# Issue 4822 phase 1 shadow pytest signal validation

## Result

PASS. The resolver, its tests, and the shadow workflow step land without
changing any existing output, consumer, or check name. The duplicate
authoritative pytest run is deliberately untouched, which is the phase 1
contract.

## Evidence

- Focused tests: 57 passed in `tests/quality_gate/test_resolve_pytest_signal.py`.
- Neighbouring suites: 611 passed across `tests/workflows/` and
  `tests/quality_gate/`.
- `pre_pr.py` passed all validations.
- `ruff check`, `ruff format --check`, and `mypy` clean on both new files.
- `actionlint` exit 0. `yamllint` warning categories and counts diffed against
  the pre-change file: identical, so the edit adds no new warning.
- Taste count ratchet measured with the new files tracked: 581 violations
  against baseline 583.

## Discrimination check

Assertions were verified to fail when the behaviour they describe is removed.
An eight-mutant harness was run from outside the repository tree, restoring a
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
| emit raw agreement reason | DEAD |
| CONTROL: comment-only edit | SURVIVED as required |

The surviving control proves the suite is not failing on unrelated edits.

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
with `shadow_pytest_agreement=AGREE` and exit 0.

## Not verified here

The shadow step has not executed under a real `GITHUB_TOKEN`. Local runs used a
personal token, so the sufficiency of `actions: read` for the workflow token is
unproven until the step runs in CI. That exposure is bounded: the step is
`continue-on-error`, every resolution outcome exits 0, and no consumer reads
its outputs, so a token failure surfaces as UNKNOWN and changes no verdict.
Measuring that, and the PENDING versus PASS disagreement rate created by the 45
minute pytest.yml budget against the 10 minute run-tests budget, is the purpose
of phase 1.
