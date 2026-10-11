# Plan: Deterministic Validate Spec Coverage (#6182)

Spec: `.project-toolkit/specs/SPEC-6182-deterministic-spec-coverage.md`.

## Milestones

### M1: Deterministic verdict script (S)

Exit: `scripts/ci/spec_coverage_verdict.py` exists, is stdlib only, and has tests for every row of the spec's verdict table.

- T1.1 Write `scripts/ci/spec_coverage_verdict.py`. Inputs: `HAS_SPECS`, `PR_BODY` (env), fallback to `gh pr view` on `workflow_dispatch` when the body is empty. Reuses `scripts/external_signals/acceptance_criteria.py`. Writes verdict, reason, and unchecked items to `GITHUB_STEP_SUMMARY`. Exit 0 on PASS, 1 on FAIL, 2 on config error (ADR-035). Done: runs under bare `python3`.
- T1.2 Tests in `tests/ci/test_spec_coverage_verdict.py`: no spec, no section, numbered list only, one unchecked, all checked, repeat run returns same result, dispatch fetch failure exits 2.

### M2: Split the workflow (M)

Exit: `ai-spec-validation.yml` has no environment, secret, or ai-review step. `ai-spec-review.yml` holds the model review.

- T2.1 `ai-spec-validation.yml`: job `validate-spec` (name `Validate Spec Coverage`) keeps checkout, Decide scope, Extract Spec References, then runs the verdict script. Drop `environment: agent-claude`, both ai-review steps, Load Spec Content, Prepare Spec Context, external-signal gate, report, comment, summary, and Check for Failures. Keep the debounce job.
- T2.2 New `ai-spec-review.yml`: same `pull_request` and `workflow_dispatch` triggers, job `review-spec` with `environment: agent-claude`. Steps: scope, refs, load, prepare, trace, completeness, report generation, post comment, job summary. Every model step keeps `continue-on-error` plus its `report_advisory_result.py` step. No step fails the job on a verdict.
- T2.3 Delete code left with no caller: `.github/scripts/check_spec_failures.py`, `scripts/ci/spec_external_signal_wrapper.py`, `scripts/quality_gate/spec_external_signal_gate.py`, and their tests. Keep `gate_aggregator.py` (other callers).
- T2.4 Repoint tests that read the model steps from `ai-spec-validation.yml` to `ai-spec-review.yml`: `test_spec_validation_workflow_wiring.py`, `test_spec_declaration_reaches_both_reviewers.py`, `test_advisory_step_reporting_wiring.py`, `test_invoke_claude_review.py`, `test_pr_merge_ready_advisory_agent_checks.py` (`EXPECTED_JOB_ENVIRONMENTS`). Delete `tests/workflows/test_ai_spec_validation_fail_closed.py`. Add a test that `validate-spec` has no `environment`, no `secrets.`, and no ai-review step.

### M3: Config and docs (S)

Exit: no doc describes the check as model-driven.

- T3.1 Add `ai-spec-review.yml` to `advisory_agent_workflows` in `.claude/skills/pr-review/pr-review-config.yaml` (source template if generated). Keep `ai-spec-validation.yml` listed (owner D3) with a reason that names the deterministic check.
- T3.2 Remove the `Validate Spec Coverage` entry from `.project-toolkit/pr-checks/dispositions.json`.
- T3.3 Update `templates/rules/ci-scripts.md` rule 18 list, then run `uv run python build/scripts/build_all.py`.
- T3.4 Update `.agents/governance/GOTCHAS.md` spec coverage entry, `FAIL-OPEN-INVENTORY.md` rows, `bypass-allowlist.json` entries, `.github/PULL_REQUEST_TEMPLATE.md` comment, `push-pr` skill text.
- T3.5 ADR-114: add a dated note naming the new workflow. Write the debate log the ADR review rule requires.

## Dependency graph

M1 before T2.1. T2.2 and T2.3 parallel after T2.1. T2.4 after T2.1 to T2.3. M3 after M2.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Verdict script imports a third-party module and fails under bare `python3` | Low | Check red on every PR | Test runs it with `sys.executable -I` style subprocess; stdlib-only check |
| A doc or test still names the deleted scripts | Medium | Pre-PR wiring check red | `git grep` for each deleted name before commit |
| New workflow not on advisory list | Low | Pending approval blocks readiness | T3.1 plus existing `EXPECTED_JOB_ENVIRONMENTS` test |
| Generated mirror drift | Medium | `Generated Artifact Staleness` red | Run `build_all.py` after template edits |

## Deferred

- Issue AC to file mapping and named-test signals.
- Removing `ai-spec-validation.yml` from `advisory_agent_workflows`.

## Revisions after critic review

- T1.1 prints an `::error::` line on FAIL. The no-section message names the `## Acceptance criteria` heading. T1.2 asserts both.
- T2.2 adds a `concurrency` group keyed on the PR number with `cancel-in-progress: true`, so edits do not stack approval-gated runs. No debounce job.
- T2.3 also fixes references to the deleted scripts in `.github/scripts/generate_spec_report.py`, `scripts/ci/invoke_claude_review.py`, `scripts/external_signals/__init__.py`, and `scripts/external_signals/acceptance_criteria.py`. `generate_spec_report.py` stops naming `Validate Spec Coverage` as its check. Delete `tests/test_check_spec_failures.py`.
- T2.4 also covers `tests/ci/test_spec_coverage_scope.py` and `tests/ci/test_spec_extract_refs.py` (extend to both workflows), `tests/ci/test_ci_scripts_are_wired.py:151` text, and `tests/test_pr_merge_ready_advisory_agent_checks.py` (`LISTED`, the old `EXPECTED_JOB_ENVIRONMENTS` key replaced by `("ai-spec-review.yml", "review-spec")`). The new test asserts no `./.github/actions/ai-review` anywhere in `ai-spec-validation.yml`.
- T3.1 edits `src/claude/skills/pr-review/pr-review-config.yaml`, then `build_all.py` mirrors it.
- T3.3 also updates `tests/build_scripts/fixtures/rule_templates_b2/expected/ci-scripts.md` if the build test compares it.
- T3.4 edits `templates/skills/push-pr.SKILL.md.tmpl`, not the rendered copies.
- T3.2 lands in the same PR as T2.1.
- `measure_workflow_coalescing.py` defaults stay unchanged (out of scope).
