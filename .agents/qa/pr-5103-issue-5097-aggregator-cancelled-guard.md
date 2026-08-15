---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14714-issue-5097-aggregator-cancelled-guard.json
qaCommit: 370ed63034b0f0383928f5f75941309f9e543a50
---
# QA Report: Aggregator Cancellation Guard (Issue #5097)

## Verdict: PASS

## What changed

Five result-aggregator jobs moved from `if: always()` to `if: !cancelled()`.
Each reads its dependencies' outcomes and exits non-zero on anything but
success, and each sits in a workflow with `cancel-in-progress` enabled, so
before this change a superseded run published a red check run against the pull
request head.

| Workflow | Job | Before | After |
|---|---|---|---|
| pytest.yml | test-result | `always() && (needs.check-paths.result != 'success' \|\| needs.check-paths.outputs.python-changed == 'true')` | same with `!cancelled()` in place of `always()` |
| pytest.yml | main-failure-alert | `always() && github.event_name == 'push' && github.ref_name == github.event.repository.default_branch` | same with `!cancelled()` in place of `always()` |
| cli-smoke.yml | smoke-result | `always()` | `${{ !cancelled() }}` |
| installed-plugin-hook-guard.yml | guard-result | `always()` | `${{ !cancelled() }}` |
| test-codeql-integration.yml | aggregate-results | `always()` | `${{ !cancelled() }}` |

## Contract evidence

Read from the vendor, not from memory. GitHub's expressions reference states
that `always()` "Causes the step to always execute, and returns true, even when
canceled", and gives the substitution directly: "If you want to run a job or
step regardless of its success or failure, use the recommended alternative:
`if: ${{ !cancelled() }}`".

Two consequences the fix depends on:

1. A guarded job still runs when a dependency FAILED or was SKIPPED. That
   preserves the cli-smoke pass-through for the no-CLI-change case (#1168) and
   the plugin-hook guard's refusal to report success when its matrix never ran
   (#4672).
2. A guarded job skips while the run is being cancelled. A skipped job
   publishes no check run, and a skipped check is not a success, so branch
   protection keeps waiting instead of merging on a false green.

YAML note: a plain scalar beginning with `!` parses as a YAML tag, so each
condition uses either the existing `>-` block scalar or `${{ }}`. All 64
workflow files parse under `yaml.safe_load` after the change.

## Audit scope

Every workflow under `.github/workflows/` was parsed and classified. The shape
that produces #5097 is: a job with `needs`, in a workflow triggered by
`pull_request` or `push`, whose steps read `needs.<job>.result` or
`toJSON(needs)`.

- 24 jobs carry both `needs` and `always()`.
- 7 of those consume dependency results on a PR head. All 7 are now guarded.
- 2 of the 7 were already guarded by the #2347 fix and are untouched:
  `ai-pr-quality-gate.yml::aggregate` and `ai-session-protocol.yml::aggregate`,
  both `always() && !cancelled()`. The `always()` term there is redundant, not
  wrong.
- 5 were unguarded and are the table above.

Left alone, with reasons:

| Workflow | Job | Reason |
|---|---|---|
| nightly-cli-smoke.yml | smoke-result | `schedule` and `workflow_dispatch` only; never reports on a PR head |
| pr-maintenance.yml | summarize | `schedule` and `workflow_dispatch` only |
| backlog-triage.yml | summarize, recommend | `schedule` and `workflow_dispatch` only |
| codeql-analysis.yml | check-blocking-issues | `always()` on a PR head, but it never reads `needs.<job>.result`; it scores downloaded SARIF. Outside the shape. Flagged as a follow-up: a cancelled run can still leave it red on missing artifacts. |
| ai-pr-quality-gate.yml | 14 review jobs | Gate on `needs.check-changes.result == 'success'` in their own `if`; they do not convert dependency results into an exit code |
| ai-spec-validation.yml | check-paths, validate-spec | Same shape as the review jobs above |

Step-level `if: always()` inside jobs (cleanup and artifact-upload steps) was
not touched. Those are correct uses.

## Test results

| Suite | Tests | Result |
|---|---|---|
| tests/workflows/test_aggregator_cancellation_guard.py | 33 | PASS |
| tests/workflows/test_pytest_xdist_parallelism.py | 45 | PASS |
| tests/test_plugin_hook_guard_aggregate.py | 22 | PASS |
| tests/workflows/test_quality_gate_aggregate_cancel_skip.py | 6 | PASS |
| tests/ci/test_merge_group_readiness.py | 15 | PASS |

The last two are not modified by this change. They are the two suites most
likely to break on an aggregate `if` edit: one pins the #2347 guard, the other
pins the required-context to producer-job mapping. Both stay green.

## Coverage

Per `.agents/governance/TESTING-RIGOR.md` and `.claude/rules/testing.md` MUST 9,
every assertion runs against `yaml.safe_load` output, never workflow text.

- Positive, 5 parametrized jobs x 3 assertions: guarded on cancellation, no
  bare `always()`, still reads a dependency result.
- Negative, 5 parametrized controls: each job is rebuilt on a deep copy
  carrying the exact `if` it had on `origin/main`, and the same checker the
  positive cases use must reject it.
- Sweep: no `pull_request` or `push` workflow may carry an unguarded
  result-consuming aggregator, asserted repository-wide with no allowlist.
  The sweep also asserts it examined at least 7 aggregator jobs, so a
  classifier that stops matching fails instead of reporting a clean tree
  (`.claude/rules/testing.md` MUST 10).
- Sweep controls: a synthetic unguarded aggregator must be reported, a
  schedule-only one must not, and the PyYAML boolean `on:` key must still
  resolve.
- Edges: missing `if`, missing `needs`, the `cancelled() == false` spelling, a
  success-only condition, and the redundant `always() && !cancelled()` spelling
  (accepted semantically, rejected on spelling).
- Concurrency pin: each of the four affected workflows must keep
  `cancel-in-progress` enabled, so reverting cancellation cannot be mistaken
  for this fix.

## Mutation evidence

The guard was proved non-vacuous by restoring the defect. Rewriting
`cli-smoke.yml::smoke-result` back to `if: always()` failed exactly three
tests, all naming that job:

- `TestFixedAggregators::test_aggregator_skips_a_cancelled_run[cli-smoke.yml::smoke-result]`
- `TestFixedAggregators::test_aggregator_drops_bare_always[cli-smoke.yml::smoke-result]`
- `TestRepositoryWideSweep::test_every_pr_head_aggregator_is_guarded`

The remaining 30 tests passed, so the failure is attributable to the mutated
job rather than to a harness that fails unconditionally. The mutation was
reverted and the suite returned to 33 passed.

## Mirror obligation

Two existing tests pinned the old contract and were flipped in the same change,
not deleted:

- `tests/workflows/test_pytest_xdist_parallelism.py::TestAggregateJob::test_aggregate_runs_when_path_detection_fails`
- `tests/test_plugin_hook_guard_aggregate.py::test_guard_result_runs_even_when_dependencies_fail`

Both now assert `!cancelled()` is present and `always()` is absent, and both
carry the reason in their docstrings so the next reader does not re-add
`always()` believing the aggregate would otherwise stop reporting.

## Validation

- `uv run python scripts/validation/pre_pr.py`: all checks PASS, including
  Workflow YAML Validation, YAML Style Validation, Workflow Local Run, Mypy
  Changed Files (ratchet), and Count Ratchets.
- `uv run ruff check` and `uv run ruff format --check` clean on every file this
  change authors.
- `uv run mypy tests/workflows/test_aggregator_cancellation_guard.py`: no
  issues. The workflow-document parameters are typed `Mapping[Any, Any]`
  because PyYAML resolves an unquoted `on:` key to the boolean `True`; no
  suppression was used.
- All 64 files under `.github/workflows/*.yml` parse under `yaml.safe_load`.

## Security

`scripts/validation/detect_infrastructure.py` (via the `infrastructure-advisory`
pre-commit job) flagged all four workflow files CRITICAL and asked for a
security agent review. The change alters no permission block, no action pin, no
secret handling, and no `run:` body. It narrows when four jobs execute. The
`installed-plugin-hook-guard.yml` false-green protection is preserved because a
skipped job is not a success for branch protection. Routing to the security
agent is still recommended by protocol.

## Known gaps

1. `codeql-analysis.yml::check-blocking-issues` keeps `always()`. It is outside
   the fixed shape (it reads SARIF, not `needs.<job>.result`), but a cancelled
   run can still leave it red on missing artifacts. Worth its own issue.
2. `ai-pr-quality-gate.yml::aggregate` and `ai-session-protocol.yml::aggregate`
   keep the redundant `always() && !cancelled()` spelling, so the repository
   now carries two spellings of one guard. Cosmetic, deliberately out of scope.
3. The fix cannot be exercised end to end from this container: proving a
   cancelled run publishes no check requires a real superseded run on GitHub.
   Confirm on the pull request by pushing twice in quick succession and
   checking that the cancelled run's aggregate jobs report skipped rather than
   failure.
4. Serena and Forgetful MCP were unreachable in this container, so no memory
   was written. The durable finding lives in the new test module's docstring
   and in this report.
