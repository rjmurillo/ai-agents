# Design Review: ADR-026 Debounce & Concurrency Evaluation

Date: 2026-01-06
Analyst: Architect

## Scope
Evaluate ADR-026 compliance for:
- Debounce enablement paths (workflow input + `vars.ENABLE_DEBOUNCE` for PR runs)
- Conditional propagation (`needs: debounce`) to gate first jobs
- Concurrency group fallback `${{ github.event.pull_request.number || inputs.pr_number }}` for `workflow_dispatch`

## Findings

- Debounce enablement: Implemented in
  - `.github/workflows/ai-pr-quality-gate.yml` (inputs + `vars.ENABLE_DEBOUNCE`)
  - `.github/workflows/ai-spec-validation.yml` (inputs + `vars.ENABLE_DEBOUNCE`)
  Evidence: conditional `if: (workflow_dispatch && inputs.enable_debouncing) || (pull_request && vars.ENABLE_DEBOUNCE == 'true')`, and `uses: ./.github/actions/workflow-debounce`.

- Debounce propagation: Present as first job `debounce` with downstream `needs: debounce` and `always()` gating, allowing both success and skipped paths to proceed.

- Concurrency group fallback: Present in the above two workflows for both `concurrency.group` and debounce input `concurrency-group`, using `${{ github.event.pull_request.number || inputs.pr_number }}`. Other workflows using per-PR concurrency groups are PR-only and do not define `workflow_dispatch`, so fallback is not required.

## Verdict
Compliant for targeted workflows (AI PR Quality Gate, Spec Validation). Pattern is correctly applied and propagated. No blocking issues identified.

## Recommendations
- Repository variable: Ensure `vars.ENABLE_DEBOUNCE` exists and is managed via ops runbook; value must be the string `'true'` to enable on PR runs.
- Consistency note: ADR-026 example shows `cancel-in-progress: false` (queueing). Current workflows use `cancel-in-progress: true`. Update ADR-026 to reflect chosen strategy and rationale to avoid confusion.
- Reuse pattern if extended: If additional workflows later support both PR and `workflow_dispatch` and use per-PR concurrency groups, adopt the same fallback expression and `debounce` gating.

## Required Changes
- Documentation-only: Update ADR-026 Implementation snippet to match current usage (`cancel-in-progress: true`) and clarify best-effort coalescing trade-off already discussed.

## Traceability
- ADR: `.agents/architecture/ADR-026-pr-automation-concurrency-and-safety.md`
- Workflows: `ai-pr-quality-gate.yml`, `ai-spec-validation.yml`
