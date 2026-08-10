---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10025-pr-4587.json
qaCommit: 544521f4f57006a8c668f591baa1ae05900649bd
---
# Test Report: PR #4587 CI job hygiene

## Scope

Branch `fix/ci-job-hygiene`, code tip
`544521f4f57006a8c668f591baa1ae05900649bd`, against merge-base
`8108ebfea285f7030906a425be28d8707680d001`.

Seven files changed, 190 insertions and 15 deletions. The change adds a finite
pytest job timeout, passes the base ref to the CLI exit ratchet, isolates CI
environment variables in subprocess tests, and pins those contracts.

## Conflict resolution

Merging current `main` produced one diff3 conflict in
`tests/ci/test_write_copilot_synthesis_summary.py`. Both branches reworded the
same comment. The executable guard was identical. Resolution kept main's
canonical wording plus the branch's Issue #4541 citation.

Verification:

- all four marker forms absent, including `|||||||`
- `GITHUB_STEP_SUMMARY` guard appears once
- `full_env.pop` appears once
- seven synthesis-summary tests pass normally
- the same seven pass with `GITHUB_STEP_SUMMARY` set

## Merge artifact found by local CI prompt

The first merge push preserved two copies of
`cli-exit-contract-ratchet` in both `lefthook.yml` and
`scripts/validation/checks_ratchet.py`. The local Architect prompt reproduced
the remote Critical finding. One copy was removed from each registry.

Verification:

- each registry contains the name exactly once
- 70 ratchet and Lefthook parity tests pass
- `pre_pr.py` passes

## Timeout decision evidence

Issue #4502 records two observations:

- GitHub run `30830624080`: pytest 986 seconds, complete job 17.2 minutes
- one parallel-fleet pytest run: 1546 seconds, the worst observation

This is an operational guardrail from two observations, not a percentile.
Thirty minutes leaves four minutes beyond the worst pytest observation.
Sixty minutes leaves 34 minutes but doubles hang time versus 30. Forty-five
minutes is the selected midpoint and leaves 19 minutes for setup, coverage
gates, and artifact upload.

The contract test now asserts exactly 45 minutes. Changing the workflow to 60
turns it red. Re-measure before changing the limit when either one legitimate
run reaches 45 minutes, or three non-cancelled runs exceed 36 minutes within
30 days. One infrastructure failure is not evidence to raise the ceiling.

## Deterministic gates

| Command | Result |
|---------|--------|
| Five affected test files | 79 passed |
| `scripts/validation/pre_pr.py` | all validations passed |
| Dash scan on authored files | 0 occurrences |

## Local AI quality gate

Ran the ten canonical files under `.github/prompts/pr-quality-gate-*.md`
against `CONTEXT_MODE: full` and the complete local diff before the final
push.

| Axis | Result |
|------|--------|
| Security | PASS |
| QA | PASS |
| Analyst | PASS |
| Architect | PASS after duplicate removal |
| DevOps | PASS |
| Roadmap | PASS |
| Reliability | PASS |
| Agent Safety | PASS |
| Observability | WARN, no structured timing events; explicitly optional |
| Decision Rigor | Real evidence gaps fixed; final output self-contradicted and referenced unrelated content |

The final Decision Rigor output invented a PR body about raw judge responses
and failed scoring cells, then said its own High findings were unsupported.
No code in this diff matches those claims. The supported timeout findings
were addressed: measurement source, sample size, runtime scope, alternatives,
exact policy, false-timeout failure mode, and a measurable review trigger.

## Verdict

PASS. All supported Critical and High findings are fixed. The remaining
Observability WARN recommends structured events only if operators need
per-ratchet timing, which is outside this PR's scope.
