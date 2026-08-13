---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14705-fix-4778-copilot-auth-preflight.json
qaCommit: fc03c9160ec5e28bae4b11196f94fac89f5fa0a4
---

# QA Report: Issue 4778 Copilot preflight

## Scope

Validated the infrastructure preflight rewrite, the review gating change, and
the infrastructure-skip artifact path on branch `fix/4778-copilot-auth-preflight`
at commit `fc03c9160ec5e28bae4b11196f94fac89f5fa0a4`.

## Acceptance criteria

| Criterion (issue #4778) | Evidence |
| --- | --- |
| Probe the credential used by Copilot CLI, not the runner token identity | `TestCopilotAuthProbe::test_the_probe_uses_the_copilot_token_not_the_runner_token` asserts the subprocess env sets `GH_TOKEN` and `GITHUB_TOKEN` to the Copilot credential while the ambient runner token is set to a different value |
| Expose binary availability and Copilot authentication as separate outputs | `TestRenderOutputs::test_binary_and_auth_are_separate_outputs` asserts `copilot-available=true` with `auth-valid=false`; the action declares `copilot-available`, `copilot-auth-status`, `auth-valid`, and `reviews-enabled` |
| Reviewer execution follows the preflight result | `TestQualityGateWiring` asserts all ten review steps pass `infra-ready: ${{ needs.infra-check.outputs.reviews-enabled == 'true' }}` and that no `should-run` expression still references `copilot-available` |
| An infrastructure skip still produces explicit review artifacts | `tests/ci/test_infra_skip_gate_chain.py` runs save, `validate_artifact_download.find_missing`, aggregate, and `check_critical_failures` in workflow order: no artifact missing, final verdict `DID_NOT_RUN`, gate exit 1 |
| Tests cover valid credential, rejected credential, missing binary, and runner installation-token behavior | `TestCopilotAuthClassification` and `TestStatusGrading` cover valid, rejected, absent, unverified, missing binary, and the `Resource not accessible by integration` installation-token shape |

## Evidence

- `uv run pytest tests/ci/ tests/workflows/ tests/quality_gate/
  tests/test_aggregate_quality_verdicts.py -q` passed 3207 tests, 11 skipped,
  in 103.29 seconds.
- Targeted suites for the changed modules passed 146 tests: 66 in
  `test_check_agent_infrastructure.py`, 26 in `test_agent_review_outcome.py`,
  6 in `test_infra_skip_gate_chain.py`, 15 in
  `test_agent_review_save_results.py`, 28 in
  `test_agent_review_check_verdict.py`, 5 in
  `test_agent_review_generate_summary.py`.
- `uv run ruff check scripts/ci/ tests/ci/` passed. The 9 remaining repository
  ruff findings are in files this branch does not touch
  (`scripts/migrations/`, `scripts/validate_pr_review_config.py`,
  `tests/validation/`).
- `uv run python scripts/ci/adr006_run_block_scanner.py` reported 0 violations.
- `uv run python scripts/validation/run_workflow_local_test.py --files
  .github/workflows/ai-pr-quality-gate.yml --no-full`: actionlint passed; the
  local `act` run was skipped because repository secrets are absent locally.
- `uv run python scripts/ci/merge_tree_ratchet_check.py`: OK against
  `origin/main` for all five registered ratchets (ruff 27, taste 580,
  type-ignore 44, memory-index 377, cli exit contract 27).
- `uv run python scripts/validation/pre_pr.py`: the only failure was the
  type-ignore ratchet at +1, fixed in `fc03c9160e` and re-verified above.

## Old-contract tests flipped

Two tests asserted that an empty verdict always means `NEEDS_REVIEW`. That
fallback now applies only when the preflight was ready, so both now state
`INFRA_READY=true` explicitly:

- `tests/ci/test_agent_review_save_results.py::test_empty_verdict_defaults_to_needs_review`
- `tests/ci/test_agent_review_check_verdict.py::test_empty_verdict_defaults_to_needs_review_blocking`

## Residual risk

The probe cannot be exercised against a real installation token locally. The
first CI run on this PR is the live check: the Infrastructure Check summary
should read `Copilot auth: valid (user: ...)` instead of the former
`Authentication: FAILED`, and `Agent reviews: ENABLED`.

## Verdict

PASS. All five acceptance criteria have named test evidence. No QA finding
remains.
