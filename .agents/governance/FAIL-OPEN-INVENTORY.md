# Fail-Open Inventory

Every place in this repository where a check can fail to prove its contract and
the run still reports success. One row per path.

Scope: local git hooks, `scripts/validation/`, `.github/workflows/`,
`.github/scripts/`, path-filtered job skips, and bypass markers.

## What this file records, and what it does not

This file records **observed behavior on a named ref**. Each row says what the
path does today: what makes it fail open, what the caller sees, and whether the
degradation is visible anywhere. Every row was read at the cited line, not
inferred from a name or a docstring.

This file does **not** assign target behavior. Whether a given path should
become blocking, stay advisory, or be retired is a policy call with an owner,
and several of these paths are deliberate designs whose reasons are recorded in
the code. Issue #5636 lists the target classification, owner, and expiry as
separate acceptance criteria for exactly that reason. The `Target` column is
`UNDECIDED` on every row that has not had that call made, and `UNDECIDED` is an
honest state, not a gap in the survey.

Recording the current state first is what makes the policy call reviewable: the
argument for keeping a path advisory is much easier to weigh when the blast
radius of that choice is written down next to it.

## Column definitions

| Column | Meaning |
|---|---|
| `Path` | File and line where the fail-open branch lives. |
| `Trigger` | The condition that makes the check stop proving its contract. |
| `Caller sees` | The exit code, status, or state the caller actually observes. |
| `Class` | Observed today: `BLOCKING`, `ADVISORY`, `INFORMATIONAL`, or `RETIRED`. |
| `Visible` | Whether the degradation is surfaced: `yes`, `partial`, or `no`. |
| `Contract` | `TYPED` if the path reports through `scripts/validation/evidence.py`, `BOOLEAN` otherwise, `N/A` for workflow YAML. |
| `Documented` | `DELIBERATE` when the code or a comment states the reason, `UNDOCUMENTED` otherwise. |
| `Target` | The policy call. `UNDECIDED` until an owner makes it. |

`Class` is observed, not aspirational. A check is `BLOCKING` when its non-zero
exit actually stops a push or a merge today. A check wired into a workflow that
carries `continue-on-error: true` is `ADVISORY` no matter what its name
suggests, because nothing downstream reads its failure.

`Visible: partial` means the degradation appears somewhere a person could find
it (a log line, a job summary) but nothing machine-readable carries it, so no
gate and no dashboard can count it.

## How this inventory was produced

Enumerated against `main` at `16ed125` by four independent scans, one per
surface, each required to cite a line it had actually opened:

1. `.github/workflows/**` for `continue-on-error`, shell suppressions
   (`|| true`, `|| :`, `|| echo`, `2>/dev/null` on a check command, `set +e`),
   and steps whose failure is never re-asserted.
2. Path-filtered job skips, separating a filter that scopes a diff-scoped
   validator (legitimate) from one that hides a whole-tree validator behind a
   diff (the defect class `.claude/rules/ci-scripts.md` names as "Path filters
   gate the diff, never the tree").
3. `scripts/validation/**` and `.github/scripts/**` for guard clauses that
   return success because a dependency, ref, or file was absent, for
   exception handlers that swallow a check, and for soft-warn modes that
   default to non-blocking.
4. Bypass markers, environment variables, and CLI flags that disable or
   downgrade a check, recording whether the authorization is machine-verified
   or prose.

## Prior art this inventory does not re-litigate

Issue #2808 hardened four workflows against this same class:
`audit-hook-bypass.yml`, `pytest.yml` (bandit step), `memory-validation.yml`,
and `drift-detection.yml`. Issue #5626 later deleted `memory-validation.yml`
outright as fully redundant, so three of the four remain live. `tests/workflows/test_workflow_fail_open_guards.py`
pins those contracts so the suppression cannot return without a test failing
first. Those four are listed below as `RETIRED` rows so a later reader does not
rediscover them as open findings.

## Bypass markers and escape hatches

Anything that disables or downgrades a check. `Authorization` records whether
the repository machine-verifies who may use it.

| Path | Mechanism | Disables | Who can set it | Authorization | Auditable | Target |
|---|---|---|---|---|---|---|
| `.github/workflows/agent-drift-detection.yml:17,58-72,118-121` | commit marker `[skip-drift-check]`, grepped from `git log BASE..HEAD` | the `validate` job, the regenerate-vs-committed diff check | any contributor who can write a commit message on the PR | detection machine-verified, authorization PROSE-ONLY | yes, job summary plus commit history | UNDECIDED |
| `.github/workflows/agent-drift-detection.yml:207-229` | three unchecked `- [ ]` markdown boxes naming the marker's preconditions | nothing; they are the stated preconditions for the row above | whoever writes the PR description | PROSE-ONLY, no CODEOWNERS check, no required-reviewer call, no branch-protection tie found in the file | partial, the checklist renders but nothing marks it complete or blocks on unchecked boxes | UNDECIDED |
| `lefthook.yml:81,87,149,272,280,293,303,313,324,332,368,376,389`, `checks_tooling.py:252`, `pre_pr.py:472,477`, `.github/actions/setup-code-env/action.yml:158-164` | `SKIP_AUTOFIX=1` | autofix-only jobs; the paired `-check` and lint jobs still run | anyone locally, plus a CI action input `skip-autofix` defaulting to `0` | NONE, an unauthenticated toggle | no, stdout only (`verify_code_env.py:128-129`) | UNDECIDED | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->
| `scripts/validation/git_hook_policy.py:6826-6828` | `SKIP_YAMLLINT=1` | the `yaml-advisory` job | anyone locally | NONE | no, stdout only | UNDECIDED |
| `scripts/validation/git_hook_policy.py:2340-2342` | `SKIP_RETROSPECTIVE_GATE=true` | the `retrospective-policy` pre-push job | anyone locally before push | NONE | no, stdout only | UNDECIDED |
| `scripts/detect_scope_explosion.py` (removed) | `SKIP_SCOPE_CHECK=1` | previously the `scope-policy` and `branch-scope` gates | n/a | RESOLVED by removal, ADR-100 item 4, issue #5241: item 3 demoted both gates to advisory first, then the flag and its handling were deleted, so there is nothing left to bypass | n/a | RESOLVED |
| `scripts/validation/check_push_lock_before_commit.py:45-56,71,78,178-179` | `SKIP_PUSH_LOCK_COMMIT_GUARD=1` | the `push-lock-commit-guard` pre-commit probe (issue #5123 race guard) | anyone locally | NONE | no, stdout only | UNDECIDED |
| `scripts/validation/run_workflow_local_test.py:24-25,88,93` | `SKIP_WORKFLOW_LOCAL_TEST=true` or `1` | the `workflow-local-run` job | anyone locally | NONE | UNCLEAR, the module header claims "the bypass is logged, not hidden"; the consuming branch was not read, so what "logged" writes and to whom is unverified | UNDECIDED |
| `lefthook.yml:177-180` | `skip:` when `SKIP_ACTIONLINT=1` **or** `actionlint` is absent from PATH | the whole `actionlint` pre-commit job | anyone locally, and automatically on any machine without actionlint installed | NONE | no, lefthook prints "(skip)" only | UNDECIDED |
| `lefthook.yml:74-390`, roughly 19 jobs | lefthook's built-in `skip: - merge` tag | 19 pre-commit gates on any commit lefthook classifies as a merge | anyone producing a merge commit, so not an opt-in flag at all | NONE, an unconditional structural skip | no, only lefthook's per-job "(skip)" line | UNDECIDED |
| `.claude/rules/universal.md` MUST NOT item 2 | `LEFTHOOK`, `LEFTHOOK_EXCLUDE`, `LEFTHOOK_BIN`, config override, direct hook edit, `--no-verify` | hook execution wholesale | anyone with local shell access | NONE by construction; these are lefthook's own variables, so grepping this repository for them returns nothing and no repo-side audit exists | no repo-side audit found | forbidden by rule already; enforcement surface UNDECIDED |

One decoy, recorded so a later reader does not mistake it for a hatch:
`git_hook_policy.py:7787-7792` reads `SKIP_CLI_E2E`, then rejects it, printing
`ERROR: SKIP_CLI_E2E=true cannot bypass a required CLI E2E gate` and exiting 2.
Setting it hardens the gate rather than skipping it.

## Local hook jobs that report success without proving their contract

Advisory by design in most cases. The column that matters is `Trigger`: several
of these return success not because they found nothing, but because they could
not run at all, and the two outcomes print differently only to a human reading
stdout.

| Path | Trigger | Caller sees | Class | Visible | Contract | Target |
|---|---|---|---|---|---|---|
| `git_hook_policy.py:6825-6839` (`yaml-advisory`) | yamllint findings, and separately a missing yamllint binary caught as `FileNotFoundError` | `return 0` either way; findings print as `WARNING` | ADVISORY | partial | BOOLEAN | UNDECIDED |
| `git_hook_policy.py:6886-6899` (`planning-advisory`) | any exit code from `validate_planning_artifacts.py` | always `return 0` | ADVISORY | partial | BOOLEAN | UNDECIDED |
| `git_hook_policy.py:6902-6925` (`taste-advisory`) | findings present; a scan crash still blocks | findings never block, crash does | ADVISORY | partial | BOOLEAN | DELIBERATE, docstring says "Advisory covers findings, not failures" |
| `git_hook_policy.py:7722-7738` (`additions-advisory`) | findings, and separately `git diff --numstat` itself failing | always `return 0`; the failed-measurement path prints `WARNING: could not calculate branch additions` and passes | ADVISORY | partial | BOOLEAN | UNDECIDED |
| `git_hook_policy.py:7848-7873` (`bot-cascade-advisory`) | `gh` binary absent, or no PR resolvable | `return 0` with "Bot cascade check skipped"; the named check never ran | ADVISORY | partial | BOOLEAN | UNDECIDED |
| `git_hook_policy.py:7663-7688` (`run_workflow_local`) | child exit code 4, "unrunnable locally, needs secrets absent from this environment" | converted to `0`; the job reports PASS though `act` never executed the workflow | ADVISORY | partial | BOOLEAN | DELIBERATE, the exit 4 contract is documented at `run_workflow_local_test.py:65-68` |
| `lefthook.yml:605-607` (`worktree-gc-report`) | any non-zero exit of the script | swallowed inline by `\|\| echo "... ignored because this job is advisory (issue 4257)"` | ADVISORY | partial | N/A | DELIBERATE, reason inline |
| `lefthook.yml:652-655` (`python-lint-advisory`), `lefthook.yml:142-149` (`python-autofix`) | any ruff violation | `ruff check --exit-zero`, so violations structurally cannot produce a non-zero exit | ADVISORY | partial | N/A | UNDECIDED | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->
| `lefthook.yml:218-224,672-675` plus `.claude/skills/security-detection/detect_infrastructure.py:135-195` | any finding, including the CRITICAL branch | `main()` returns `0` at every path, lines 168, 172, and 195, so "CRITICAL: Security agent review REQUIRED" prints to stdout and the job passes | ADVISORY | partial, no structured sink | BOOLEAN | UNDECIDED, and this is the row a reviewer should look at first | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->
| `.github/workflows/audit-hook-bypass.yml:63-68` plus `scripts/detect_hook_bypass.py:11-14` | commits showing `--no-verify` indicators | detects, never blocks; the "Report findings" step re-invokes the detector with `\|\| true` | INFORMATIONAL | yes, uploads `hook-bypass-audit.json` and posts a `::warning::` | N/A | DELIBERATE, audit by design, the artifact is the trail | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->

## Validators under `scripts/validation/` and `.github/scripts/`

`Contract` distinguishes a gate reporting through the typed states added in
#5641 from one still on the boolean contract. A TYPED row is not automatically
safe: two of them below reach `PASS` or a licensed `BLOCKED` with a real
finding or an absent tool underneath.

| Path | Function | Trigger | Caller sees | Class | Contract | Visible | Documented |
|---|---|---|---|---|---|---|---|
| `check_serena_memory_worktree_scope.py:373-384` | `validate_serena_memory_worktree_scope` | any finding, and separately `git worktree list` failing | unconditional `True` | ADVISORY | BOOLEAN | partial | DELIBERATE, "always returns True" |
| `check_tmp_worktrees.py:305-318` | `validate_tmp_worktrees` | any finding, and separately `git worktree list` failing | unconditional `True` | ADVISORY | BOOLEAN | partial | DELIBERATE |
| `checks_spec.py:361-397` | `validate_spec_contradiction` | any subprocess exit code, including the script being missing | `return True` at :397 | ADVISORY | BOOLEAN | yes | DELIBERATE, "the WARN output is the signal" |
| `active_plan_closeout.py:159-176` | `validate_active_plan_closeout` | any closeable-plan warning | `return True` at :176 | ADVISORY | BOOLEAN | partial | DELIBERATE |
| `checks_dash.py:144-175` | `validate_dash_prohibition` | base ref unresolved, or `git diff` fails | `return True` | ADVISORY on failure-to-run, BLOCKING on findings | BOOLEAN | yes | DELIBERATE, "fail open" stated |
| `checks_dash.py:107-127` | `_find_dash_violations` | `git show HEAD:<path>` non-zero for one changed file | that file is silently dropped from the scan, no count adjustment | BLOCKING gate, narrowed scope | BOOLEAN | no | UNDOCUMENTED at runtime; the source comment is invisible in output |
| `check_canonical_citations.py:310-312` | `main` | violations found with `STRICT_CANONICAL_CHECK` unset, the default | exit 0 despite violations | ADVISORY | BOOLEAN | yes | DELIBERATE, "Failure mode by default: WARNING (exit 0)" |
| `checks_spec.py:306-334` | `validate_canonical_citations` | soft-warn mode, per the row above | `bool(exit_code == 0)`, and the exit code is 0 | ADVISORY | BOOLEAN | yes | DELIBERATE |
| `checks_spec.py:337-349` | `validate_orchestrator_citations` | `check_orchestrator_citations.py` absent | `return True` | ADVISORY | BOOLEAN | yes | DELIBERATE |
| `checks_copilot.py:11-16` | `validate_copilot_routing_exclusions` | `FileNotFoundError`, the copilot-cli template is missing | `return True` | ADVISORY | BOOLEAN | yes | DELIBERATE |
| `checks_coverage.py:54-103` | `validate_review_marker` | `REVIEW_MARKER_ENFORCED` unset (default) and either the script is missing or the marker check fails | `return True` | ADVISORY | BOOLEAN | yes | DELIBERATE, escalate with `REVIEW_MARKER_ENFORCED=1` |
| `check_git_hook_health.py:387-400`, via `:468` | `_evaluate` | `GITHUB_ACTIONS` or `CI` is set | `return 0`, 0 hooks probed | ADVISORY under CI | BOOLEAN | yes | DELIBERATE, and worth a second look: the check exists to catch an inert pre-push hook and disables itself in the one environment that could report it centrally |
| `checks_tooling.py:524-616`, esp. `:603-613` | `validate_yaml_style` | yamllint exits non-zero with real style violations | `CheckOutcome.passed(...)`, so the state itself is PASS and the violation survives only in `scope` and `detail` strings | ADVISORY | TYPED | partial | DELIBERATE, "findings warn, never fail" |
| `evidence.py:580-593`, `:595-605` | `default_pre_pr_policy` exceptions | `validate_workflow_yaml` or `validate_yaml_style` returns BLOCKED because actionlint or yamllint is absent | the BLOCKED state is recorded and printed, then the policy licenses it and the aggregate stays non-blocking | ADVISORY by policy | TYPED | yes | DELIBERATE, each carries a named justification |
| `git_hook_policy.py:2432-2452` | `check_branch_context` | five distinct conditions: merge in progress, no sessions dir, branch undetermined, no session log, no branch field | `return 0` at all five sites, with no print on any of them | ADVISORY | BOOLEAN | no, silent | DELIBERATE, "deliberately fail-open on every ambiguous input" |
| `active_plan_closeout.py:103-156` | `gh_issue_state` | `gh` missing, timeout, OSError, non-zero exit, or unparseable state | returns `None`; the caller then treats the issue as non-terminal and drops it from the warning | ADVISORY | BOOLEAN | partial, warns per lookup, but "unknown" and "genuinely open" become indistinguishable downstream | DELIBERATE per call, the conflation itself UNDOCUMENTED |
| `.github/scripts/validate_investigation_claims.py:337-372` | `_run_diff_validation` | any violation count | `return 0` at :372 | ADVISORY | N/A | yes, `::warning::` annotation | DELIBERATE, "advisory, always 0" |
| `.github/scripts/check_spec_failures.py:82-87,108-112` | `main` | `TRACE_INFRA_FAILURE` or `COMPLETENESS_INFRA_FAILURE`, either or both | `return 0`, "Not blocking merge" | ADVISORY | N/A | yes, `::warning::` | DELIBERATE for the not-blocking decision; UNDOCUMENTED that the infra-failure flag is trusted without independent verification |
| `.github/scripts/check_design_review_gate.py:132-136` | `run_gate` | no `DESIGN-REVIEW-*.md` files exist | "Gate passes", `return 0` | INFORMATIONAL | N/A | yes | borderline, an empty-scope pass rather than a fail-open; recorded so the next reader does not re-triage it |

### Coverage limit on this section

This section is a **lower bound, not a closed set**. `git_hook_policy.py` is
8,454 lines and `check_skill_md_portability.py` 1,464, both measured at
`16ed125`; each was sampled by targeted grep and context reads, not read end to
end. `scripts/validation/` holds 125 Python files, and those the grep passes did
not hit were not opened. `check_branch_context` alone holds five silent fail-open sites in one
function, which is the reason to expect more in the unread regions.

Do not read the absence of a path from this table as evidence that the path is
clean. `.claude/rules/universal.md` MUST NOT item 9 forbids asserting an
absence from a partial search, and this search was partial by construction.

## GitHub Actions workflows

25 constructs across `.github/workflows/*.yml`. There are no `.yaml` files, and
`2>/dev/null` returns zero matches repo-wide.

Grouped by how much the swallow actually costs. A `continue-on-error` whose
outcome a later step re-asserts is a different animal from one nothing reads.

### Group 1: swallowed, never re-asserted, no reason recorded

The rows to look at first. Nothing downstream reads the outcome and no comment
says why.

| Path | Workflow | Job.step | Construct | What fails silently | Visible |
|---|---|---|---|---|---|
| `skill-passive-compliance.yml:90` | Skill/Passive Context Compliance | `validate-compliance` / Run skill description budget | `continue-on-error: true` | a budget overrun or a script crash never fails the job, and no step reads the outcome | no |
| `ai-spec-validation.yml:220` | Spec-to-Implementation Validation | `validate-spec` / Post PR Comment | `continue-on-error: true` | the report comment failing to post | no |
| `drift-detection.yml:47` | Agent Drift Detection | `detect-drift` / Emit K2 kill-criteria event | `continue-on-error: true` | kill-criteria metrics emission failure | no |
| `drift-detection.yml:74` | Agent Drift Detection | `detect-drift` / Upload kill-criteria events | `continue-on-error: true` | the drift-events artifact upload failing | no |
| `agent-drift-detection.yml:66` | Agent Drift Detection (CI) | `check-paths` / Check for bypass marker | `grep -c ... \|\| true` | any grep fault collapses to "no bypass", indistinguishable from a real tool failure | no |

### Group 2: on a workflow that gates a required PR check

| Path | Job.step | Construct | What fails silently | Visible | Documented |
|---|---|---|---|---|---|
| `memory-health.yml:88` | `health-check` / Run health check (Markdown) | `continue-on-error: true` | a `memory_enhancement` crash on the markdown path. Unlike the JSON path below, nothing re-asserts it: the only consumer is the PR-comment step, which wraps `readFileSync('health-report.md')` in try/catch and posts "Health check completed but no report generated." | partial | UNDOCUMENTED |
| `pr-validation.yml:134` | `validate-pr` / Post PR Comment | `continue-on-error: true` | the validation report failing to post | partial, retry wrapper only | UNDOCUMENTED |
| `ai-spec-validation.yml:154` | `validate-spec` / Requirements Traceability Check | `continue-on-error: true` | an analyst-agent crash or timeout at step level | partial, `check_spec_failures.py` reads `TRACE_VERDICT` and `TRACE_INFRA_FAILURE` downstream | UNDOCUMENTED |
| `ai-spec-validation.yml:169` | `validate-spec` / Completeness Check | `continue-on-error: true` | a critic-agent crash or timeout | partial, same downstream gate | UNDOCUMENTED |
| `memory-validation.yml:133` | `validate-memories` / Generate health report | `\|\| true` | RESOLVED by deletion, issue #5626: the workflow no longer exists, so the construct cannot run | n/a | was DELIBERATE, and the stated guard covered the JSON at :123, not this markdown file |
| `memory-validation.yml:112` | `validate-memories` / Verify all memories | `set +e`, rc captured and tolerated | RESOLVED by deletion, issue #5626 | n/a | was DELIBERATE |
| `audit-hook-bypass.yml:68` | `detect-bypass` / Report findings | `\|\| true` | a second, redundant detector invocation swallows its own exit code, including the `>=2` crash contract | no | DELIBERATE for exit 1; the reasoning does not cover the crash path on this re-invocation |

### Group 3: scheduled or async workflows, not required checks

| Path | Job.step | What fails silently | Visible | Documented |
|---|---|---|---|---|
| `drift-detection.yml:63` | `detect-drift` / Summarize kill-criteria drift telemetry | the report exits 1 when a criterion fired | partial, alert lands in the job step summary | DELIBERATE |
| `post-pr-retrospective.yml:150` | `retrospective` / Run retrospective via Claude Code | an expired OAuth token, an API outage, any real agent error | partial, step annotation | DELIBERATE, Issue #2015, "the annotation, not a red check, is the signal" |
| `pr-maintenance.yml:95` | `discover-prs` / Detect orphan commits | detector failures and findings alike | no, raw run log only | DELIBERATE, Issue #4316, "Warn, never block" |
| `pr-validation.yml:161-165` | `validate-pr` / Check PR commit count | a transient GitHub API failure degrades to `status=UNKNOWN` and exit 0 | no | DELIBERATE, issues #3262 and #5233 |
| `pr-validation.yml:175` | `validate-pr` / Apply needs-split label | a label API outage on add | partial | DELIBERATE, Issue #2557 |
| `pr-validation.yml:183` | `validate-pr` / Remove needs-split label | the same on removal | partial | DELIBERATE, Issue #2557 |
| `ai-spec-validation.yml:193` | `validate-spec` / External-signal gate (observe) | the deterministic acceptance-criteria check failing | partial, job summary; explicitly not yet authoritative | DELIBERATE |

### Group 4: swallowed at step level, re-asserted by an explicit downstream gate

Lowest risk. Recorded because the construct is present and a later edit could
remove the re-assertion without touching the `continue-on-error` line.

| Path | Job.step | Re-asserted by |
|---|---|---|
| `agent-drift-detection.yml:138` | `validate` / Regenerate and validate agent files | "Fail when any drift check fails" reads `steps.validate.outcome` and exits 1 |
| `agent-drift-detection.yml:150` | `validate` / Check plugin lib mirrors are in sync | same step |
| `agent-drift-detection.yml:156` | `validate` / Check plugin manifest parity | same step |
| `semantic-pr-title-check.yml:45` | `main` / `amannn/action-semantic-pull-request` | "Classify outcome (ignore Unicorn HTML flake, block real failures)" |
| `memory-health.yml:83` | `health-check` / Run health check (JSON) | "Parse health results" runs `parse_memory_health_results.py` with no `continue-on-error`; that script returns 1 on a missing, empty, unparseable, or schema-invalid report, so a crashed health command fails the job |
| `software-engineering-library-activation.yml:79` | `activation-gate` / Run live activation eval | "Fail when live activation gate failed" reads `steps.live-eval.outcome == 'failure'` and exits 1, alongside the rollback alert issue |

### Excluded after reading

Not fail-open, recorded so the next scan does not re-triage them:
`test-codeql-integration.yml:101,139`; the `memory-validation.yml` `set +e`
pairs that ended in an explicit `exit $rc`, now moot since issue #5626 deleted
that workflow; `pytest.yml:600`, which is a comment about a historical or
avoided pattern rather than a live construct; and `if: always()` artifact
uploads plus the deliberate no-op skip jobs in `codeql-analysis.yml` and
`pr-maintenance.yml`. 2026-09-11: the `auto-assign-reviewer.yml:64` entry
above was retired; that workflow was deleted as a dead compatibility shell
for the disabled `rjmurillo-bot.yml` (epic #5456 cohort 3).

### Scope limit on this section

Findings on the `Visible` column are bounded by what the workflow YAML and step
outputs show. Python internals invoked from a `run:` step were read only where
they appear in the validator section above. Where a script's behavior on empty
or malformed input would move a `partial` to `yes` or `no`, that is unresolved.

## Path-filtered job skips

The defect class `.claude/rules/ci-scripts.md` names: "Path filters gate the
diff, never the tree." A filter is legitimate when the gated command only
inspects the changed files, or when the filter's glob covers the validator's
whole input domain. It is a defect when a whole-tree validator sits behind a
diff filter, because a pre-existing violation then goes unreported while the
check still reports success.

30 candidates: 24 `dorny/paths-filter` workflows and 6 with a top-level
`on: paths:` trigger. Each verdict was decided by reading the called Python
module, not the workflow YAML alone. 6 defects, 24 legitimate, 0 unclear.

### Defects

| Path | Gated job | Command | Why it is a defect |
|---|---|---|---|
| `codeql-analysis.yml:77` | `analyze` | `github/codeql-action/analyze` | CodeQL always scans the whole codebase per language and takes no file arguments. A plain push or PR that misses the `scannable` filter skips it. `FORCE_RUN_EVENTS: schedule,merge_group` at :95 mitigates rather than eliminates, and only if the merge queue is actually in use |
| `pytest.yml:74` filter, `:275,:313` steps | `test` | `ruff_count_ratchet.py`, `subprocess_encoding_count_ratchet.py` | both ratchets scan git-tracked files repo-wide, per `ruff_count_ratchet.py:11`, but sit inside a job gated on Python changes. The same file already extracted `zero-collection-guard` and `line-endings-guard` ungated for this exact reason, citing `ci-scripts.md` at `:100-107,130-147`, and did not extract these two |
| `agent-drift-detection.yml:79` | `validate` | `build/generate_agents.py --validate` | the filter is a strict subset of the audited filter that `validate-generated-agents.yml` uses for the identical command. Missing `docs/agent-catalog.md`, `.claude/**`, `.github/agents/**`, `.github/instructions/**`, `.github/prompts/**`, and `.github/workflows/**`, so a change to only those triggers the sibling workflow and not this one |
| `memory-health.yml:48` | `health-check` | `memory_enhancement health`, whole `.serena/memories/` tree then `verify_all_citations` | citations point at arbitrary target files anywhere in the repository. A change to a cited target outside `.serena/memories/**` and outside `scripts/**/*.py` does not trip the filter, so a citation staled by that change goes unverified |
| `memory-validation.yml:38` | `validate-memories` | `memory_enhancement verify-all` | RESOLVED by deletion, issue #5626; the same gap survives in the two rows above and below |
| `citation-verify.yml:42` | `verify-citations` | `memory_enhancement verify-all` | the same gap, and the narrowest filter of the three: not even `scripts/**/*.py` is included |

### Legitimate, and why

Recorded so a later scan does not re-triage them. Two patterns account for
most: the filter glob equals the validator's file-type or directory domain
(`yaml-lint.yml`, `validate-paths.yml`, `validate-adr-number-uniqueness.yml`,
`validate-spec-id-uniqueness.yml`, `validate-planning-artifacts.yml`,
`validate-artifact-retention.yml`, `validate-plugin-manifests.yml`,
`skillbook-validation.yml`, `slash-command-quality.yml`,
`skill-passive-compliance.yml`, `hook-contract-check.yml`,
`validate-rule-activation-coverage.yml`, `validate-plugin-version-bump.yml`,
`passive-context-budget.yml`, `cli-smoke.yml`, `vendor-provenance.yml`), or the
check is inherently PR-scoped and asks a question about this diff
(`ai-spec-validation.yml`, `investigation-claim-backstop.yml`,
`synthesis-panel-gate.yml`, `test-codeql-integration.yml`).

Three deserve their reasoning kept, because they are the shapes worth copying:

- `instruction-budget.yml:36` carries no filter at all and runs on every
  trigger. This is the already-fixed precedent `ci-scripts.md` cites.
- `validate-generated-agents.yml:48` gates a whole-tree generator diff behind a
  filter, and a co-located test, `tests/ci/test_frontmatter_gate_paths_filter.py`,
  asserts the filter still covers everything the gate scans. The filter cannot
  drift out from under the validator without that test failing.
- `agent-skill-discriminator-check.yml:54` and
  `software-engineering-library-activation.yml:10` move the whole-corpus
  measurement off the diff filter onto an unfiltered schedule trigger.

### Adjacent finding, not counted as a defect here

`investigation-claim-backstop.yml:11` has a differently shaped gap: its
top-level path filter requires an allowlisted investigation path to appear in
the diff before the workflow runs at all. A commit that falsely claims
`SKIPPED: investigation-only` while touching zero allowlisted paths is never
checked. That is a trigger inversion rather than a whole-tree-behind-a-diff
mismatch, so it is recorded here and not counted in the 6.

### Unverified for this section

No row was checked against branch protection. Every "required check" reference
in these workflows is the workflow's own comment, not a reading of
`repos/.../rules/branches/main`. The `codeql-analysis.yml` and `pytest.yml`
verdicts also assume `merge_group` events actually fire in this repository,
which the YAML alone cannot establish.

## Retired: hardened by issue #2808

Four workflows previously in this class. Each had a step meant to detect a
problem that converted its own crash, or its findings, into a green run.
`tests/workflows/test_workflow_fail_open_guards.py` pins the hardened contract
so the suppression cannot return without a test failing first.

| Path | What it was | What pins it now |
|---|---|---|
| `audit-hook-bypass.yml` detection step | `\|\| true` around the detector | the step classifies the exit code, fails on `>=2`, and treats missing JSON as a failure rather than `indicator_count=0`; the contract lives in `scripts/ci/run_hook_bypass_audit.py` per ADR-006 |
| `pytest.yml` security job | bandit behind `\|\| true` | bandit gates on high severity and confidence with no `\|\| true`; a CodeQL `upload-sarif` step publishes findings with `if: always()` |
| `memory-validation.yml` verify and parse steps | pipefail aborting before the exit code was captured, and a default-to-pass parse | nothing, and nothing needs to: issue #5626 deleted the workflow and `scripts/ci/parse_memory_validation_results.py` with it. The checks it ran are enforced by lefthook, the required `Validate PR` check, and `citation-verify.yml` |
| `drift-detection.yml` JSON re-run | stderr and the exit code both swallowed | fails on exit `>=2`, since exit 1 is the expected drift path for that step |

Note that `audit-hook-bypass.yml:68` still carries a `\|\| true`, listed in
Group 2 above. That is a second, redundant invocation added for human-readable
output, not the detection step #2808 hardened.

## Owner, expiry, and review date

Not assigned. Issue #5636 requires an owner and a review date per entry, and
neither can be derived from the code: they are assignments, not observations.
Every row above therefore carries `Target: UNDECIDED` and no owner column.

Filling those in is the next step on #5636 and is the point at which this file
stops being a survey and starts being a control. Until then, treat this file as
evidence for that conversation, not as a policy that has been agreed.

## Keeping this file honest

This inventory is prose, and prose rots. Three specific ways it will drift:

1. A new `continue-on-error: true` lands in a workflow and nobody adds a row.
2. A path listed here is hardened, and the row still says it fails open.
3. A cited line number moves and the citation silently points at the wrong code.

Nothing in this change detects any of the three. That is a real gap and it is
named here rather than papered over: a ratchet that counts fail-open constructs
per surface and fails when the count exceeds what this file records is the
mechanism that would close it, and it is not in this change.

Two smaller traps for whoever extends this file:

- `.agents/governance/` is excluded from markdown linting. Running the
  repository's markdown gate against this file reports
  `Markdown linting selected 0 of 1 target(s)`, which is a PASS meaning
  "not linted", not "clean". Do not read that PASS as a check on this file.
- Cite line numbers with the ref they were read at. Every citation here was
  read against `main` at `16ed125`.
