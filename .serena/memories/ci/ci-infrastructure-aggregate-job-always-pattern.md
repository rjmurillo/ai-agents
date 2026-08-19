# CI Infrastructure: Aggregate Job Always Pattern

**Atomicity Score**: 95%
**Date**: 2026-01-09
**Source**: Session 813 - Issue #856 RCA
**Impact**: 9/10 (Critical for multi-stage validation workflows)

## Statement

Aggregate jobs that collect results from matrix strategies MUST carry a status
check function in their `if` so they run even when validation jobs fail. Use
`!cancelled()`, not `always()`. See the correction below before applying any
example in this memory.

## Correction 2026-08-15 (Issue #5097): use `!cancelled()`, not `always()`

The half of this memory that says the job must run when a dependency FAILS is
still right. The spelling is not. `always()` also returns true while the run is
being CANCELLED, so on a workflow with `cancel-in-progress` every push that
supersedes a live run left the aggregate reading `cancelled` dependencies,
exiting non-zero, and publishing a red check run against the pull request head
for a run nobody was waiting on.

GitHub documents the substitution in its expressions reference: `always()`
"Causes the step to always execute, and returns true, even when canceled", and
"If you want to run a job or step regardless of its success or failure, use the
recommended alternative: `if: ${{ !cancelled() }}`". `!cancelled()` is a status
check function, so it keeps the enforcement gap in Issue #856 closed: the job
still runs when a dependency failed or was skipped.

**Correction 2026-08-18 (Issue #5139): the guarded job does not always "skip"
during cancellation.** GitHub re-evaluates a job's `if:` condition for every
currently running job when the run is cancelled (docs.github.com, workflow
cancellation reference): "To cancel the workflow run, the server re-evaluates
`if` conditions for all currently running jobs. If the condition evaluates to
`true`, the job will not get canceled." A job already running when
cancellation lands has `!cancelled()` flip to false on that re-evaluation and
is itself cancelled as a result, concluding `cancelled`, not the earlier
"`if:` is evaluated once, before the job starts" mechanism this correction
originally stated (a Copilot review finding on PR #5141 caught the error).
Verified against a real superseded run on this repository (`actions_get
get_workflow_run` on run `31896264033`): overall conclusion `cancelled`, with
its "Run Python Tests" and "Main failure alert" jobs both reporting
`cancelled`, not `skipped`. This memory makes no claim about the exact
conclusion a not-yet-started job reports; the guard still does its job either
way, because `cancelled` is (like `skipped`) neither `success` nor `failure`,
so branch protection keeps waiting on a superseded run rather than merging on
a false green, and neither is the red `failure` that `always()` produced.

Read every `if: always() && ...` example below as `if: !cancelled() && ...`.
Mind the YAML: a plain scalar beginning with `!` parses as a tag, so use a `>-`
block scalar or `${{ }}`.

Fixed in the five PR-head aggregators: `pytest.yml` `test-result` and
`main-failure-alert`, `cli-smoke.yml` `smoke-result`,
`installed-plugin-hook-guard.yml` `guard-result`, and
`test-codeql-integration.yml` `aggregate-results`. The two aggregates repaired
earlier for Issue #2347 (`ai-pr-quality-gate.yml`, `ai-session-protocol.yml`)
carry the equivalent `always() && !cancelled()`. The contract is pinned by
`tests/workflows/test_aggregator_cancellation_guard.py`, whose repository-wide
sweep fails any new `pull_request` or `push` aggregator that reads
`needs.<job>.result` without the guard.

## Context

When workflows have matrix validation jobs that can fail, followed by an aggregate job that must collect all results and enforce blocking conditions.

## Problem

**GitHub Actions Default Behavior**: Jobs skip when dependencies fail unless explicitly configured.

```yaml
# Anti-pattern (BUG)
validate:
  strategy:
    matrix:
      file: ${{ fromJson(needs.detect.outputs.files) }}
  steps:
    - run: exit 1  # Fails on validation error

aggregate:
  needs: [detect, validate]  # Skipped when validate fails!
  if: needs.detect.outputs.has_files == 'true'
  steps:
    - run: exit 1  # Never runs - enforcement gap!
```

**Result**: PRs can merge with validation failures because enforcement never executes.

## Evidence

**Issue #856**: Session Protocol Validation workflow allowed PRs with malformed session logs to merge via auto-merge.

**Root Cause**: `.github/workflows/ai-session-protocol.yml:249-250`

```yaml
aggregate:
  name: Aggregate Results
  needs: [detect-changes, validate]
  if: needs.detect-changes.outputs.has_sessions == 'true'  # Not enough!
```

When `validate` job failed:
1. GitHub Actions skipped `aggregate` (default behavior)
2. `if` condition never evaluated
3. Enforcement step at line 449 never ran
4. PR not blocked

## Correct Pattern

```yaml
# Correct: Use !cancelled() condition, not always() (Issue #5097 correction above)
aggregate:
  name: Aggregate Results
  needs: [detect-changes, validate]
  if: ${{ !cancelled() && needs.detect-changes.outputs.has_sessions == 'true' }}
  steps:
    - name: Collect Results
      run: |
        # Collect from all validation jobs (success or failure)
        # Build aggregate verdict
    
    - name: Enforce Blocking Conditions
      run: |
        if ($verdict -eq 'CRITICAL_FAIL') {
          exit 1  # NOW this runs and blocks PR
        }
```

**Why This Works**:
- `!cancelled()` runs the job even when dependencies fail; when the run
  itself is being cancelled (superseded by a newer push), the job either
  never starts (`skipped`) or is terminated mid-run (`cancelled`) depending
  on timing, and neither conclusion publishes the red check `always()` would
  have (see the 2026-08-18 correction above)
- Still respects other conditions (e.g., `has_sessions`)
- Enforcement step executes and can block PR
- Clear intent: "aggregate results whenever the run reaches a real verdict,
  not only when everything upstream reports the same status"

## When to Use

Apply this pattern when:
- Matrix strategy runs validations that can fail
- Aggregate job must collect all results (success or failure)
- Aggregate job enforces blocking conditions
- PR merge decision depends on aggregate output

## Related Patterns

**Job Status vs Verdict** (ci-infrastructure-003):
- Individual validation jobs should fail fast on violations
- Aggregate job should collect all verdicts
- Aggregate job determines final PR outcome

**Fail Fast Infrastructure** (ci-infrastructure-001):
- Infrastructure failures: Exit immediately (no aggregation)
- Policy violations: Complete successfully, emit verdict, aggregate decides

## Implementation Checklist

- [ ] Matrix validation jobs can fail independently
- [ ] Aggregate job has `needs: [validate]`
- [ ] Aggregate job uses `if: ${{ !cancelled() && <other-conditions> }}` (not `always()`, see Correction above)
- [ ] Aggregate job collects results from all matrix jobs
- [ ] Aggregate job enforces blocking conditions
- [ ] Test: Verify aggregate runs when validation fails
- [ ] Test: Verify enforcement blocks PR when violations exist

## Success Criteria

- Aggregate job runs even when validation jobs fail
- All validation results collected (success or failure)
- Enforcement step executes and blocks PR on violations
- No false negatives (violations missed)
- No enforcement gaps (PRs merge with violations)

## Related

- Issue #856: Session Protocol Validation enforcement gap
- Memory: ci-infrastructure-003-job-status-verdict-distinction
- Memory: ci-infrastructure-001-fail-fast-infrastructure-failures
- Analysis: .agents/analysis/session-protocol-enforcement-gap-analysis.md
