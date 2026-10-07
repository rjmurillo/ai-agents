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

Every row now carries a `Target`, an `Owner`, and an `Expiry`, filled in on
2026-09-29 under issue #5636. The observed-state columns describe the code as
read at the cited ref. The `Target` column is the policy call, made with the
rules below, and the four classes are defined in "Owner, expiry, and review
date". A row marked `C` is deliberately not decided here: it needs an owner
call, and the epic report lists the options.

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
| `Contract` | `TYPED` if the path reports through `scripts/validation/evidence.py` (or, for a self-contained skill script that cannot import it, through its parity-tested `TYPED_RESULT_VOCABULARY` mirror), `BOOLEAN` otherwise, `N/A` for a row whose construct no longer exists. A workflow or lefthook row is `TYPED` when its step or job hands its result to `scripts/ci/report_advisory_result.py`. |
| `Documented` | `DELIBERATE` when the code or a comment states the reason, `UNDOCUMENTED` otherwise. |
| `Target` | The policy call: `A` fail closed, `B` keep non-blocking, `C` owner call pending, or `RESOLVED`. |
| `Owner` | Who answers for the row. Defaults to the repository owner. |
| `Expiry` | The date the row is re-read, the PR that fixed it, or the date a `C` decision is due. |

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

| Path | Mechanism | Disables | Who can set it | Authorization | Auditable | Target | Owner | Expiry |
|---|---|---|---|---|---|---|---|---|
| `.github/workflows/agent-drift-detection.yml` (bypass steps and job removed) | commit marker `[skip-drift-check]`, removed; divergences now live in `.agents/governance/drift-allowlist.json` | the `validate` job, the regenerate-vs-committed diff check | any contributor who can write a commit message on the PR | shape-verified: the validator requires an exact `path` and a non-empty `reason` per entry and exits 2 otherwise. Whether the divergence is justified is a reviewer call; CODEOWNERS requires the owner on the allowlist file, the loader, and the generator | yes, job summary plus commit history | RESOLVED, issue #5636, PR #6056: marker and unchecked-checklist path dropped; allowlist read by `build/generate_agents.py --validate` | n/a | n/a |
| `.github/workflows/agent-drift-detection.yml` (checklist boxes removed) | three unchecked `- [ ]` markdown boxes naming the marker's preconditions, removed with the marker | nothing; they were the stated preconditions for the row above | n/a | RESOLVED by removal: the workflow no longer contains a `- [ ]` box or the marker | n/a | RESOLVED, issue #5636, PR #6056: the marker and its checklist are gone, so no prose-only precondition remains | n/a | n/a |
| `lefthook.yml:81,87,149,272,280,293,303,313,324,332,368,376,389`, `checks_tooling.py:252`, `pre_pr.py:472,477`, `.github/actions/setup-code-env/action.yml:158-164` | `SKIP_AUTOFIX=1` | autofix-only jobs; the paired `-check` and lint jobs still run | anyone locally, plus a CI action input `skip-autofix` defaulting to `0` | allowlisted with an owner, reason, and expiry in `.agents/governance/bypass-allowlist.json`; `check_bypass_allowlist.py` fails on an unlisted use and on an expired entry. Limit: the variable is still unauthenticated at run time, so the entry records that the exception is owned, not who set it, an unauthenticated toggle | no, stdout only (`verify_code_env.py:128-129`) | B: keep bypass. Only autofix jobs skip; the paired check and lint jobs still run. | rjmurillo | 2026-12-31 | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->
| `scripts/validation/git_hook_policy.py:6826-6828` | `SKIP_YAMLLINT=1` | the `yaml-advisory` job | anyone locally | allowlisted with an owner, reason, and expiry in `.agents/governance/bypass-allowlist.json`; `check_bypass_allowlist.py` fails on an unlisted use and on an expired entry. Limit: the variable is still unauthenticated at run time, so the entry records that the exception is owned, not who set it | no, stdout only | B: keep bypass. Skips only the advisory yaml job. | rjmurillo | 2026-12-31 |
| `scripts/validation/git_hook_policy.py` (removed) | `SKIP_RETROSPECTIVE_GATE=true` | previously the `retrospective-policy` pre-push job | n/a | RESOLVED by removal: the gate demanded a retrospective per calendar day or per session, so the common case was a push blocked on a write nothing had asked for. Gate, flag, and handling are deleted; retrospectives are event-triggered (Post-PR Retrospective workflow, `/retro`, `retrospective` skill) | n/a | RESOLVED | n/a | n/a |
| `scripts/detect_scope_explosion.py` (removed) | `SKIP_SCOPE_CHECK=1` | previously the `scope-policy` and `branch-scope` gates | n/a | RESOLVED by removal, ADR-100 item 4, issue #5241: item 3 demoted both gates to advisory first, then the flag and its handling were deleted, so there is nothing left to bypass | n/a | RESOLVED | n/a | n/a |
| `scripts/validation/check_push_lock_before_commit.py:45-56,71,78,178-179` | `SKIP_PUSH_LOCK_COMMIT_GUARD=1` | the `push-lock-commit-guard` pre-commit probe (issue #5123 race guard) | anyone locally | allowlisted with an owner, reason, and expiry in `.agents/governance/bypass-allowlist.json`; `check_bypass_allowlist.py` fails on an unlisted use and on an expired entry. Limit: the variable is still unauthenticated at run time, so the entry records that the exception is owned, not who set it | no, stdout only | B: keep bypass. Local race-guard probe; developer escape hatch, stdout only. | rjmurillo | 2026-12-31 |
| `scripts/validation/run_workflow_local_test.py:24-25,88,93` | `SKIP_WORKFLOW_LOCAL_TEST=true` or `1` | the `workflow-local-run` job | anyone locally | allowlisted with an owner, reason, and expiry in `.agents/governance/bypass-allowlist.json`; `check_bypass_allowlist.py` fails on an unlisted use and on an expired entry. Limit: the variable is still unauthenticated at run time, so the entry records that the exception is owned, not who set it | UNCLEAR, the module header claims "the bypass is logged, not hidden"; the consuming branch was not read, so what "logged" writes and to whom is unverified | B: keep bypass. Documented bypass for workflows that cannot run under act. The claim that it is logged was not verified here. | rjmurillo | 2026-12-31 |
| `lefthook.yml:177-180` | `skip:` when `SKIP_ACTIONLINT=1` **or** `actionlint` is absent from PATH | the whole `actionlint` pre-commit job | anyone locally, and automatically on any machine without actionlint installed | allowlisted with an owner, reason, and expiry in `.agents/governance/bypass-allowlist.json`; `check_bypass_allowlist.py` fails on an unlisted use and on an expired entry. Limit: the variable is still unauthenticated at run time, so the entry records that the exception is owned, not who set it | no, lefthook prints "(skip)" only | B: keep bypass. Local pre-commit convenience when actionlint is absent; not a required check. | rjmurillo | 2026-12-31 | <!-- citation-freshness: ignore -- the checker reads anchor names from the adjacent table rows, so this row is tested against a neighbor's names, and the row's own citation is unchanged -->
| `lefthook.yml:74-390`, roughly 19 jobs | lefthook's built-in `skip: - merge` tag | 19 pre-commit gates on any commit lefthook classifies as a merge | anyone producing a merge commit, so not an opt-in flag at all | NONE, an unconditional structural skip | no, only lefthook's per-job "(skip)" line | B: keep bypass. Lefthook merge-commit skip; the merged content was gated on its source branches. | rjmurillo | 2026-12-31 |
| `.claude/rules/universal.md` MUST NOT item 2 | `LEFTHOOK`, `LEFTHOOK_EXCLUDE`, `LEFTHOOK_BIN`, config override, direct hook edit, `--no-verify` | hook execution wholesale | anyone with local shell access | NONE by construction; these are lefthook's own variables, so grepping this repository for them returns nothing and no repo-side audit exists | no repo-side audit found | forbidden by rule already; enforcement surface B: keep bypass. Forbidden by rule already; the audit-hook-bypass workflow is the trail. | rjmurillo | 2026-12-31 |

One decoy, recorded so a later reader does not mistake it for a hatch:
`git_hook_policy.py:7787-7792` reads `SKIP_CLI_E2E`, then rejects it, printing
`ERROR: SKIP_CLI_E2E=true cannot bypass a required CLI E2E gate` and exiting 2.
Setting it hardens the gate rather than skipping it.

## Local hook jobs that report success without proving their contract

Advisory by design in most cases. The column that matters is `Trigger`: several
of these return success not because they found nothing, but because they could
not run at all, and the two outcomes print differently only to a human reading
stdout.

| Path | Function | Trigger | Caller sees | Class | Visible | Contract | Target | Owner | Expiry |
|---|---|---|---|---|---|---|---|---|---|
| `git_hook_policy.py:6845-6881` (`yaml-advisory`) | `run_yamllint` | yamllint findings, and separately a missing yamllint binary (`_run_command` catches the `OSError` itself and returns exit 3, so the old `except FileNotFoundError` never ran and a missing tool was reported as findings) | still `return 0`, and every non-pass path now prints one typed line on stderr (issue #5636): `SKIP` with `policy.env_bypass` for `SKIP_YAMLLINT=1`, `BLOCKED` with `tool.absent` for a missing yamllint or `timeout` for a kill, `FAIL` with `advisory.findings` for findings | ADVISORY | yes | TYPED | B: keep advisory. Advisory yaml lint. | rjmurillo | 2026-12-31 |
| `git_hook_policy.py:6935-6964` (`planning-advisory`) | `run_planning_advisory` | any exit code from `validate_planning_artifacts.py` | still always `return 0`; findings now print a typed `FAIL` line with `advisory.findings` on stderr, and a timeout prints `BLOCKED` with `timeout` (issue #5636) | ADVISORY | yes | TYPED | B: keep advisory. Advisory planning-artifact check. | rjmurillo | 2026-12-31 |
| `git_hook_policy.py:6967-7022` (`taste-advisory`) | `run_taste_advisory` | findings present; a scan crash still blocks | findings still `return 0` and now print a typed `FAIL` line with `advisory.findings`; a crash still blocks with exit 2 and prints a typed `FAIL` line with `script.failed` (issue #5636) | ADVISORY | yes | TYPED | DELIBERATE, docstring says "Advisory covers findings, not failures" Classified B: keep advisory. Findings advisory, crash blocks. Already correct. | rjmurillo | 2026-12-31 |
| `git_hook_policy.py:7816-7850` (`additions-advisory`) | `additions_advisory` | findings, and separately `git diff --numstat` itself failing | still always `return 0`; a failed `git diff --numstat` prints a typed `BLOCKED` line with `diff.failed` and more than 500 added lines prints a typed `FAIL` line with `advisory.findings` (issue #5636) | ADVISORY | yes | TYPED | B: keep advisory. Advisory measurement. | rjmurillo | 2026-12-31 |
| `git_hook_policy.py:7960-7997` (`bot-cascade-advisory`) | `bot_cascade_advisory` | `gh` binary absent, or no PR resolvable | still `return 0`; typed lines on stderr (issue #5636): `BLOCKED` with `tool.absent` for a missing `gh` or `timeout` for a kill, `SKIP` with `pr.unresolved` for no PR, `UNKNOWN` with `output.malformed` for unparseable output, `UNKNOWN` with `evidence.incomplete` for an incomplete thread fetch, `BLOCKED` with `lookup.failed` for a failed review query, `FAIL` with `advisory.findings` for unresolved threads or a fresh bot review | ADVISORY | yes | TYPED | B: keep advisory. Advisory; prints that it skipped. | rjmurillo | 2026-12-31 |
| `git_hook_policy.py:7745-7782` (`run_workflow_local`) | `run_workflow_local` | child exit code 4, "unrunnable locally, needs secrets absent from this environment" | child exit `4` is still converted to `0`, and now prints a typed `BLOCKED` line with `auth.unavailable`, so the job no longer reports PASS silently though `act` never executed the workflow (issue #5636) | ADVISORY | yes | TYPED | DELIBERATE, the exit 4 contract is documented at `run_workflow_local_test.py:65-68` Classified B: keep advisory. Documented exit 4 contract. | rjmurillo | 2026-12-31 |
| `lefthook.yml:605-607` (`worktree-gc-report`) | n/a | any non-zero exit of the script | still exit 0, now through `scripts/ci/report_advisory_result.py run` (inner cap 100s under the job's 2m timeout): `FAIL` with `advisory.findings` on exit 1, `BLOCKED` with `script.failed`, `timeout`, or `tool.absent` otherwise, each printed as one typed line | ADVISORY | yes | TYPED | DELIBERATE, reason inline Classified B: keep advisory. Advisory report, reason inline. | rjmurillo | 2026-12-31 | <!-- citation-freshness: ignore -- the checker reads anchor names from the adjacent table rows, so this row is tested against a neighbor's names, and the row's own citation is unchanged -->
| `lefthook.yml:652-655` (`python-lint-advisory`), `lefthook.yml:142-149` (`python-autofix`) | n/a | any ruff violation | still exit 0, now through `scripts/ci/report_advisory_result.py run`: ruff exit 1 is a typed `FAIL` with `advisory.findings`, any other non-zero exit a typed `BLOCKED` with `script.failed`, so a ruff crash no longer reads as findings. `--propagate-errors` keeps a ruff crash failing the hook, as it did under `--exit-zero`. Also applied to the `python-check` pre-commit job | ADVISORY | yes | TYPED | B: keep advisory. Advisory ruff run; a blocking ruff step runs elsewhere. | rjmurillo | 2026-12-31 | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->
| `lefthook.yml:218-224,672-675` plus `.claude/skills/security-detection/detect_infrastructure.py:135-195` | n/a | any finding, including the CRITICAL branch | with `--require-security-review` (pre-push job): exit 1 on CRITICAL unless HEAD is a `/review` marker commit binding the security axis to its parent, exit 3 when git cannot answer. Pre-commit job and default invocation still exit 0 | BLOCKING at pre-push, ADVISORY at pre-commit and by default | yes, stderr names the missing marker; `--json` carries `security_review` with a typed `state` and `reason` | TYPED | RESOLVED, issue #5636, PR #6062: pre-push blocks a CRITICAL push without a SHA-bound marker; a new commit moves HEAD off the marker and invalidates it. Pre-commit stays advisory because no marker can bind a commit that does not exist yet. Limits, stated plainly: this is a local guardrail, not a control. The marker is an empty commit carrying a trailer, so anyone with commit rights can write it; `--no-verify` skips the hook; no CI job re-checks it; only HEAD's marker is read, so a push of another ref is judged by HEAD | n/a | n/a | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->
| `.github/workflows/audit-hook-bypass.yml:63-68` plus `scripts/detect_hook_bypass.py:11-14` | n/a | commits showing `--no-verify` indicators | detects, never blocks; the "Report findings" step re-invokes the detector with `\|\| true` | INFORMATIONAL | yes, uploads `hook-bypass-audit.json` and posts a `::warning::` | N/A | DELIBERATE, audit by design, the artifact is the trail Classified B: keep advisory. Audit by design; the artifact is the trail. | rjmurillo | 2026-12-31 | <!-- citation-freshness: ignore -- multiple citations on one table row; the checker tests every anchor in the row against every cited range, so a correct citation fails on a sibling row's anchors. Each range here was read at main 16ed125 and verified individually. -->

## Validators under `scripts/validation/` and `.github/scripts/`

`Contract` distinguishes a gate reporting through the typed states added in
#5641 from one still on the boolean contract. A TYPED row is not automatically
safe: two of them below reach `PASS` or a licensed `BLOCKED` with a real
finding or an absent tool underneath.

| Path | Function | Trigger | Caller sees | Class | Contract | Visible | Documented | Target | Owner | Expiry |
|---|---|---|---|---|---|---|---|---|---|---|
| `check_serena_memory_worktree_scope.py:380-404` | `validate_serena_memory_worktree_scope` | any finding, and separately `git worktree list` failing | returns a typed result (issue #5636): `FAIL` with reason `advisory.findings` for a finding, `BLOCKED` with `listing.failed` when `git worktree list` fails, `BLOCKED` with `entries.unreadable` for an unreadable sibling, else `PASS` naming the examined count. `pre_pr_policy` licenses each pair by name, so the push is not blocked | ADVISORY | TYPED | yes | DELIBERATE, the docstring states why the gate stays advisory | B: keep advisory. Advisory worktree hygiene report. | rjmurillo | 2026-12-31 |
| `check_tmp_worktrees.py:354-392` | `validate_tmp_worktrees` | any finding, and separately `git worktree list` failing | returns a typed result (issue #5636): `FAIL` with `advisory.findings` for a worktree or low free space, `BLOCKED` with `listing.failed` or `entries.unreadable` (an unreadable entry, `.git` marker, or free-space reading), `SKIP` with `tree.absent` when the temp root is absent, else `PASS`. `pre_pr_policy` licenses each non-`PASS` pair by name, so the push is not blocked | ADVISORY | TYPED | yes | DELIBERATE | B: keep advisory. Advisory worktree hygiene report. | rjmurillo | 2026-12-31 |
| `check_in_root_worktrees.py:333-356` | `validate_in_root_worktrees` | any finding, and separately `git worktree list` failing | returns a typed result (issue #5636): `FAIL` with `advisory.findings` for an in-root worktree, `BLOCKED` with `listing.failed` or `entries.unreadable` (an unreadable entry or `.git` marker), else `PASS`. `pre_pr_policy` licenses each non-`PASS` pair by name, so the push is not blocked | ADVISORY | TYPED | yes | DELIBERATE, the docstring states why the gate stays advisory | B: keep advisory. Advisory worktree hygiene report. | rjmurillo | 2026-12-31 |
| `checks_citations.py:234-278` | `validate_spec_contradiction` | any subprocess exit code, including the script being missing | returns a typed result (issue #5636): `FAIL` with `advisory.findings` and the finding count when the script reports a contradiction at exit 0, `BLOCKED` with `script.failed` for any non-zero exit, `BLOCKED` with `output.malformed` for an unreadable report, `SKIP` with `script.absent` when the script is missing, `SKIP` with the producer's reason (`pr.unresolved`, `base_ref.unresolved`, `scope.empty`) when it printed `[SKIP]` because nothing was compared, else `PASS`. `pre_pr_policy` licenses each non-`PASS` pair by name, so the push is not blocked | ADVISORY | TYPED | yes | DELIBERATE, "the WARN output is the signal" | B: keep advisory. Advisory contradiction heuristic. | rjmurillo | 2026-12-31 |
| `active_plan_closeout.py:182-234` | `validate_active_plan_closeout` | any closeable-plan warning | returns a typed result (issue #5636): `FAIL` with `advisory.findings` for a closeable plan, `BLOCKED` with `lookup.failed` when a `gh` lookup returns no usable state, else `PASS` naming the lookup count. Each non-`PASS` pair is licensed by name | ADVISORY | TYPED | yes | DELIBERATE | B: keep advisory. Advisory closeout warning. | rjmurillo | 2026-12-31 |
| `checks_dash.py` | `validate_dash_prohibition` | base ref unresolved, or `git diff` fails | returns a typed result (issue #5636): a scan that cannot run is `FAIL` under CI (blocks, reason `base_ref.unresolved` or `diff.failed`) and `SKIP` locally with the same reason and a warning; a violation is `FAIL` with `violations.found` and the hit count; blobs git cannot read make it `BLOCKED` with `entries.unreadable`, licensed by name so the gate does not start blocking (decision D10); a clean scan is `PASS` naming the examined count. `FAIL` rather than `BLOCKED` under CI keeps the pre-PR exit code at 1 | BLOCKING under CI on failure-to-run, ADVISORY locally | TYPED | yes | DELIBERATE, local warning kept on purpose | RESOLVED, issue #5636, PR #6057: fails closed under CI, warns locally; the failed `git diff` branch takes the same path | n/a | n/a |
| `checks_dash.py:94-136` | `_find_dash_violations` | `git show HEAD:<path>` non-zero for one changed file | RESOLVED, issue #5636: the file is still dropped from the scan (unchanged decision, ADVISORY on the narrowing itself), but each skipped file now prints one typed line, `[BLOCKED] validate_dash_prohibition reason=entries.unreadable ... detail=...`, built by `_find_dash_violations` through `CheckOutcome`, and a clean run's summary line distinguishes examined count from candidate count, e.g. `1 of 2 markdown file(s) checked; 1 unreadable at HEAD, skipped` | BLOCKING gate, narrowed scope (unchanged); the narrowing is now visible | TYPED | yes, both the run-time print and stdout | DELIBERATE, source comment and printed warning agree | RESOLVED, issue #5636 (see Caller sees) | n/a | n/a |
| `check_canonical_citations.py` | `main` | violations found with `STRICT_CANONICAL_CHECK` unset, the default | exit 0 despite violations, unchanged. A separate count ratchet fails when the `STRICT_CANONICAL_CHECK=1` count rises above the baseline of 3 | ADVISORY per run, BLOCKING on growth via the ratchet | TYPED | yes, one typed line on stderr per non-pass path: `FAIL` with `advisory.findings` (soft warning) or `violations.found` (strict), `SKIP` with `tree.absent` (no scan roots); stdout and exit codes unchanged | DELIBERATE, "Failure mode by default: WARNING (exit 0)" | A: hardened by owner decision D24 (issue #5636, "Ratchet is the gate"). The D11 count ratchet, PR #6058 (`scripts/ci/canonical_citations_count_ratchet.py`), blocks any increase in the violation count. It compares the aggregate, so a removed claim can offset an added one in the same change. Existing violations stay until the ratchet count is lowered. | rjmurillo | fixed in #6058 |
| `checks_citations.py:142-181` | `validate_canonical_citations` | soft-warn mode, per the row above | returns a typed result (issue #5636): `FAIL` with `advisory.findings` and the count when the soft-warn report has findings at exit 0 (licensed, so unchanged non-blocking), `FAIL` with `violations.found` on exit 1 (strict mode) or `script.failed` on any other non-zero exit, both blocking as before, `SKIP` with `script.absent` or `tree.absent`, `BLOCKED` with `output.malformed` for an unreadable report, else `PASS` | ADVISORY | TYPED | yes | DELIBERATE | A: hardened by owner decision D24 (issue #5636, "Ratchet is the gate"). The D11 count ratchet, PR #6058 (`scripts/ci/canonical_citations_count_ratchet.py`), blocks any increase in the violation count. It compares the aggregate, so a removed claim can offset an added one in the same change. Existing violations stay until the ratchet count is lowered. | rjmurillo | fixed in #6058 |
| `checks_citations.py:184-231` | `validate_orchestrator_citations` | `check_orchestrator_citations.py` absent | returns a typed result (issue #5636): `FAIL` with `script.absent` when the validator is missing and `FAIL` with `violations.found` (exit 1), `script.failed` (any other exit), or a timeout or signal reason, all unlicensed so all block as before, else `PASS` | ADVISORY | TYPED | yes | DELIBERATE | A: fail closed. Fixed in #6044. | rjmurillo | fixed in #6044 |
| `checks_copilot.py:31-71` | `validate_copilot_routing_exclusions` | `FileNotFoundError` raised while scanning a shipped skill file (a missing copilot-cli template raises `RoutingConfigError` instead, which already fails) | returns a typed result (issue #5636): `SKIP` with `tree.absent` when a skill file the scan reads is not found (still non-blocking; it names the path the OS reported), `FAIL` with `violations.found` for a violation and `FAIL` with `validator.raised` for any other raise, including a missing template (both block as before), else `PASS` | ADVISORY | TYPED | yes | DELIBERATE | B: keep advisory. The FileNotFoundError branch is dead code for a missing template: that case raises RoutingConfigError, which the broad handler already turns into a failure. An absent skills tree or empty exclusion set still passes with nothing scanned; recorded, not decided. | rjmurillo | 2026-12-31 |
| `checks_coverage.py:70-135` | `validate_review_marker` | `REVIEW_MARKER_ENFORCED` unset (default) and either the script is missing or the marker check fails | returns a typed result (issue #5636): `PASS` naming `HEAD` for a valid marker; advisory mode returns `FAIL` with `advisory.findings` for any non-zero exit (licensed) and `SKIP` with `script.absent`; `REVIEW_MARKER_ENFORCED` returns unlicensed `FAIL` with `violations.found` or `script.absent`, so it blocks | ADVISORY | TYPED | yes | DELIBERATE, escalate with `REVIEW_MARKER_ENFORCED=1` | B: keep advisory. Escalates with REVIEW_MARKER_ENFORCED=1. | rjmurillo | 2026-12-31 |
| `check_git_hook_health.py:387-400`, via `:468` | `_evaluate` | `GITHUB_ACTIONS` or `CI` is set | `return 0`, 0 hooks probed, now with a typed `SKIP` line on stdout: `policy.exempt` under CI, `tree.absent` for no lefthook config or no git repository | ADVISORY under CI | TYPED | yes | DELIBERATE, and worth a second look: the check exists to catch an inert pre-push hook and disables itself in the one environment that could report it centrally | B: keep advisory. Local hooks do not exist in CI, so a CI skip is a not-applicable skip. | rjmurillo | 2026-12-31 |
| `checks_tooling.py:625-737` | `validate_yaml_style` | yamllint exits non-zero with real style violations | `FAIL` with `advisory.findings` and the count of located findings on stdout (issue #5636), licensed for this validator by `pre_pr_policy`, so the gate does not block. A non-zero exit that printed no finding (a yamllint configuration error) is `BLOCKED` with `script.failed`, also licensed. An absent yamllint is `BLOCKED` with `tool.absent`, also licensed. A killed or timed-out yamllint is `UNKNOWN` and blocks. Findings used to read `PASS` with the exit code in `detail` | ADVISORY | TYPED | yes | DELIBERATE, "findings warn, never fail" | B: keep advisory. Findings warn by design; state is TYPED. | rjmurillo | 2026-12-31 |
| `evidence.py:580-593`, `:595-605` | `default_pre_pr_policy` exceptions | `validate_workflow_yaml` or `validate_yaml_style` returns BLOCKED because actionlint or yamllint is absent | the BLOCKED state is recorded and printed, then the policy licenses it and the aggregate stays non-blocking | ADVISORY by policy | TYPED | yes | DELIBERATE, each carries a named justification | B: keep advisory. Each license carries a named justification. | rjmurillo | 2026-12-31 |
| `git_hook_policy.py:2384-2474` | `check_branch_context` | five distinct conditions: merge in progress, no sessions dir, branch undetermined, no session log, no branch field | still `return 0` at every fail-open site, and each now prints one typed `SKIP` line on stderr naming its reason (`git.merge_in_progress`, `tree.absent`, `branch.undetermined`, `evidence.incomplete`, `policy.exempt`); the swallowed-exception handler prints a typed `UNKNOWN` line with `validator.raised` and the exception in a `detail=` field (issue #5636) | ADVISORY | TYPED | yes | DELIBERATE, "deliberately fail-open on every ambiguous input" | B: keep advisory. Deliberate on ambiguous input; silent by design. | rjmurillo | 2026-12-31 |
| `active_plan_closeout.py:115-168` | `gh_issue_state` | `gh` missing, timeout, OSError, non-zero exit, or unparseable state | still returns `None` on a failed lookup, but `validate_active_plan_closeout` now counts those and reports `BLOCKED` with reason `lookup.failed`, so "unknown" and "genuinely open" no longer read alike downstream (issue #5636) | ADVISORY | TYPED | yes at the gate: `validate_active_plan_closeout` reports `BLOCKED` with `lookup.failed`. The function still returns `None`, and each failed lookup prints one typed line naming `tool.absent`, `timeout`, `lookup.failed`, or `output.malformed` | DELIBERATE per call, the conflation itself UNDOCUMENTED | B: keep advisory. Advisory lookup. | rjmurillo | 2026-12-31 |
| `.github/scripts/validate_investigation_claims.py:337-372` | `_run_diff_validation` | any violation count | `return 0` at :372 | ADVISORY | N/A | yes, `::warning::` annotation | DELIBERATE, "advisory, always 0" | B: keep advisory. Advisory annotation. | rjmurillo | 2026-12-31 |
| `.github/scripts/check_spec_failures.py:102-123` | `main` | `TRACE_INFRA_FAILURE` or `COMPLETENESS_INFRA_FAILURE`, either or both | `return 1` with `::error::` naming the operator action (check the `ANTHROPIC_API_KEY` secret, check Anthropic rate limits); a real `FAIL` on the other side still returns 1 first | BLOCKING | N/A | yes, `::error::`, an `INFRA_FAILURE` label on the affected side and the overall verdict (`generate_spec_report.py`), and a non-zero `Check for Failures` step | RESOLVED, issue #5738: owner decision to fail closed, following `.claude/rules/security.md` MUST 7 ("gate availability is gate correctness"). Before this change the path returned 0 ("Not blocking merge") on either or both infra flags, so `Validate Spec Coverage` went green without validating anything while `COPILOT_GITHUB_TOKEN` failed. Owner decision D28 then moved this workflow's reviewer from Copilot CLI to Claude through the Anthropic Messages API (`scripts/ci/invoke_claude_review.py`, `provider: claude` in the `ai-review` action, secret `ANTHROPIC_API_KEY`); the workflow no longer reads `COPILOT_GITHUB_TOKEN`. Pinned by `tests/test_check_spec_failures.py` (both-side, single-side, truthy-flag spellings, and a passing-run control). The earlier UNDOCUMENTED note is resolved for this workflow: on the Claude path the flag comes from a typed `anthropic.APIError`, an empty reply, a missing context file, or a missing `ANTHROPIC_API_KEY` (each pinned by `tests/ci/test_invoke_claude_review.py`), not from an output regex, so a model reply containing the word "timeout" cannot set it. It stays true for the other `ai-review` callers on Copilot CLI, where the flag is still trusted without independent verification (`is_infrastructure_failure` at `scripts/ci/invoke_copilot_cli.py:220-225` returns `True` for exit codes 124 or 137, `True` for ANY empty stdout, and otherwise `True` only when stderr matches `INFRASTRUCTURE_PATTERN` and stdout holds no `VERDICT:`), but a misclassification now produces a false block, not a false pass. Operational state: the Copilot quota failure (run 36582405642, 2026-09-29T14:33Z) is moot for this workflow because Copilot is removed from it. AC1 and AC2 now map to the `ANTHROPIC_API_KEY` secret: a missing, invalid, or out-of-credit key produces a red `Check for Failures` step whose `::error::` names the secret | RESOLVED, issue #5738 and #6043 | n/a | n/a |
| `.github/scripts/check_design_review_gate.py:132-136` | `run_gate` | no `DESIGN-REVIEW-*.md` files exist | "Gate passes", `return 0` | INFORMATIONAL | N/A | yes | borderline, an empty-scope pass rather than a fail-open; recorded so the next reader does not re-triage it | B: keep advisory. Empty-scope pass, not a fail-open. | rjmurillo | 2026-12-31 |

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

Every `continue-on-error` below has an entry in `.agents/governance/bypass-allowlist.json` (owner, reason, expiry), and `check_bypass_allowlist.py` fails on one that does not.

Grouped by how much the swallow actually costs. A `continue-on-error` whose
outcome a later step re-asserts is a different animal from one nothing reads.

### Group 1: swallowed, never re-asserted, no reason recorded

The rows to look at first. Nothing downstream reads the outcome and no comment
says why.

| Path | Workflow | Job.step | Construct | What fails silently | Visible | Contract | Target | Owner | Expiry |
|---|---|---|---|---|---|---|---|---|---|
| `skill-passive-compliance.yml:90` | Skill/Passive Context Compliance | `validate-compliance` / Run skill description budget | `continue-on-error: true` | a budget overrun or a script crash never fails the job, and no step reads the outcome | no | N/A | RESOLVED: no continue-on-error in this workflow on main b0e96997f | n/a | n/a |
| `ai-spec-validation.yml:220` | Spec-to-Implementation Validation | `validate-spec` / Post PR Comment | `continue-on-error: true` | the report comment failing to post | yes, typed line `[STATE] spec-report-comment reason=...`, a `::warning::`, and the step summary | TYPED | B: keep advisory. Comment posting only; carries no verdict. | rjmurillo | 2026-12-31 |
| `drift-detection.yml:47` | Agent Drift Detection | `detect-drift` / Emit K2 kill-criteria event | `continue-on-error: true` | kill-criteria metrics emission failure | yes, typed line for `drift-k2-event` | TYPED | B: keep advisory. Telemetry emission. | rjmurillo | 2026-12-31 |
| `drift-detection.yml:74` | Agent Drift Detection | `detect-drift` / Upload kill-criteria events | `continue-on-error: true` | the drift-events artifact upload failing | yes, typed line for `drift-events-upload` | TYPED | B: keep advisory. Artifact upload. | rjmurillo | 2026-12-31 |
| `agent-drift-detection.yml` (bypass marker step, removed) | Agent Drift Detection (CI) | `check-paths` / Check for bypass marker | `grep -c ... \|\| true`, removed | RESOLVED, issue #5636, PR #6056: the marker step and its `grep` are gone, so the construct cannot run | n/a | N/A | RESOLVED, PR #6056 | n/a | n/a |

### Group 2: on a workflow that gates a required PR check

| Path | Job.step | Construct | What fails silently | Visible | Contract | Documented | Target | Owner | Expiry |
|---|---|---|---|---|---|---|---|---|---|
| `memory-health.yml:88` | `health-check` / Run health check (Markdown) | `continue-on-error: true` | a `memory_enhancement` crash on the markdown path. Unlike the JSON path below, nothing re-asserts it: the only consumer is the PR-comment step, which wraps `readFileSync('health-report.md')` in try/catch and posts "Health check completed but no report generated." | yes, typed line for `memory-health-markdown` | TYPED | UNDOCUMENTED | B: keep advisory. Markdown report only; the JSON path is re-asserted. | rjmurillo | 2026-12-31 |
| `pr-validation.yml:134` | `validate-pr` / Post PR Comment | `continue-on-error: true` | the validation report failing to post | yes, typed line for `pr-validation-comment` | TYPED | UNDOCUMENTED | B: keep advisory. Comment posting only, behind a retry wrapper. | rjmurillo | 2026-12-31 |
| `ai-spec-validation.yml:154` | `validate-spec` / Requirements Traceability Check | `continue-on-error: true` | an analyst-agent crash or timeout at step level | yes, typed line for `spec-traceability-check`, plus the downstream `check_spec_failures.py` gate | TYPED | UNDOCUMENTED | A: fail closed. Fixed in #6043: the gate reads the step outcome. | rjmurillo | fixed in #6043 |
| `ai-spec-validation.yml:169` | `validate-spec` / Completeness Check | `continue-on-error: true` | a critic-agent crash or timeout | yes, typed line for `spec-completeness-check`, plus the downstream gate | TYPED | UNDOCUMENTED | A: fail closed. Fixed in #6043: the gate reads the step outcome. | rjmurillo | fixed in #6043 |
| `memory-validation.yml:133` | `validate-memories` / Generate health report | `\|\| true` | RESOLVED by deletion, issue #5626: the workflow no longer exists, so the construct cannot run | n/a | N/A | was DELIBERATE, and the stated guard covered the JSON at :123, not this markdown file | RESOLVED by deletion, issue #5626 | n/a | n/a |
| `memory-validation.yml:112` | `validate-memories` / Verify all memories | `set +e`, rc captured and tolerated | RESOLVED by deletion, issue #5626 | n/a | N/A | was DELIBERATE | RESOLVED by deletion, issue #5626 | n/a | n/a |
| `audit-hook-bypass.yml:68` | `detect-bypass` / Report findings | `\|\| true` | a second, redundant detector invocation swallows its own exit code, including the `>=2` crash contract | yes, typed line for `hook-bypass-report`: `FAIL` with `advisory.findings` on exit 1, `BLOCKED` with `script.failed` on a crash | TYPED | DELIBERATE for exit 1; the reasoning does not cover the crash path on this re-invocation | B: keep advisory. Redundant second invocation; the hardened detection step already failed on a crash. | rjmurillo | 2026-12-31 |

### Group 3: scheduled or async workflows, not required checks

| Path | Job.step | What fails silently | Visible | Contract | Documented | Target | Owner | Expiry |
|---|---|---|---|---|---|---|---|---|
| `drift-detection.yml:63` | `detect-drift` / Summarize kill-criteria drift telemetry | the report exits 1 when a criterion fired | yes, typed `FAIL` with `advisory.findings` for `drift-telemetry-summary` when the report exits 1 | TYPED | DELIBERATE | B: keep advisory. Alert by design. | rjmurillo | 2026-12-31 |
| `post-pr-retrospective.yml:150` | `retrospective` / Run retrospective via Claude Code | an expired OAuth token, an API outage, any real agent error | yes, typed line for `post-pr-retrospective`, plus the step annotation | TYPED | DELIBERATE, Issue #2015, "the annotation, not a red check, is the signal" | B: keep advisory. Issue #2015 annotation contract. | rjmurillo | 2026-12-31 |
| `pr-maintenance.yml:95` | `discover-prs` / Detect orphan commits | detector failures and findings alike | yes, typed line for `orphan-commit-report`: `FAIL` with `advisory.findings` on exit 1, `BLOCKED` on a crash | TYPED | DELIBERATE, Issue #4316, "Warn, never block" | B: keep advisory. Issue #4316 warn-never-block contract. | rjmurillo | 2026-12-31 |
| `pr-validation.yml` | `validate-pr` / Check PR commit count | RESOLVED by deletion, ADR-100, issue #5241: the step no longer exists, so the construct cannot run | n/a | N/A | was DELIBERATE, issues #3262 and #5233 | RESOLVED by deletion, ADR-100 | n/a | n/a |
| `pr-validation.yml` | `validate-pr` / Apply needs-split label | RESOLVED by deletion, ADR-100, issue #5241: the step no longer exists, so the construct cannot run | n/a | N/A | was DELIBERATE, Issue #2557 | RESOLVED by deletion, ADR-100 | n/a | n/a |
| `pr-validation.yml` | `validate-pr` / Remove needs-split label | RESOLVED by deletion, ADR-100, issue #5241: the step no longer exists, so the construct cannot run | n/a | N/A | was DELIBERATE, Issue #2557 | RESOLVED by deletion, ADR-100 | n/a | n/a |
| `ai-spec-validation.yml:193` | `validate-spec` / External-signal gate (observe) | the deterministic acceptance-criteria check failing | yes, typed `FAIL` with `advisory.findings` for `spec-external-signal-gate`, plus the job summary | TYPED | DELIBERATE | B: keep advisory. Observe-only until the canary in PR #2361 decides; re-review then. | rjmurillo | 2026-12-31 |

### Group 4: swallowed at step level, re-asserted by an explicit downstream gate

Lowest risk. Recorded because the construct is present and a later edit could
remove the re-assertion without touching the `continue-on-error` line.

| Path | Job.step | Re-asserted by | Target | Owner | Expiry |
|---|---|---|---|---|---|
| `agent-drift-detection.yml:138` | `validate` / Regenerate and validate agent files | "Fail when any drift check fails" reads `steps.validate.outcome` and exits 1 | B: keep blocking via downstream gate. Re-asserted by the downstream gate. | rjmurillo | 2026-12-31 |
| `agent-drift-detection.yml:150` | `validate` / Check plugin lib mirrors are in sync | same step | B: keep blocking via downstream gate. Re-asserted by the downstream gate. | rjmurillo | 2026-12-31 |
| `agent-drift-detection.yml:156` | `validate` / Check plugin manifest parity | same step | B: keep blocking via downstream gate. Re-asserted by the downstream gate. | rjmurillo | 2026-12-31 |
| `semantic-pr-title-check.yml:45` | `main` / `amannn/action-semantic-pull-request` | "Classify outcome (ignore Unicorn HTML flake, block real failures)" | B: keep blocking via downstream gate. Re-asserted by the classify step. | rjmurillo | 2026-12-31 |
| `memory-health.yml:83` | `health-check` / Run health check (JSON) | "Parse health results" runs `parse_memory_health_results.py` with no `continue-on-error`; that script returns 1 on a missing, empty, unparseable, or schema-invalid report, so a crashed health command fails the job | B: keep blocking via downstream gate. Re-asserted by the parse step. | rjmurillo | 2026-12-31 |
| `software-engineering-library-activation.yml:79` | `activation-gate` / Run live activation eval | "Fail when live activation gate failed" reads `steps.live-eval.outcome == 'failure'` and exits 1, alongside the rollback alert issue | B: keep blocking via downstream gate. Re-asserted by the downstream gate. | rjmurillo | 2026-12-31 |

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

| Path | Gated job | Command | Why it is a defect | Target | Owner | Expiry |
|---|---|---|---|---|---|---|
| `codeql-analysis.yml` | `analyze` | `github/codeql-action/analyze` | CodeQL scans the whole tree per language, so a plain push or PR that misses the `scannable` filter skips it. The PR filter stays. `merge_group` already forced a full run; a nightly `schedule` (cron `23 5 * * *`, was weekly) now bounds a missed run to one day | RESOLVED, issue #5636, PR #6059: nightly schedule added, PR filter kept, merge_group run already forced | n/a | n/a |
| `pytest.yml` (`count-ratchet-guard` job, `test` job ratchet steps) | `test` | `ruff_count_ratchet.py`, `subprocess_encoding_count_ratchet.py` | both ratchets scan git-tracked files repo-wide. PR #6036 already removed the job-level gate from `test`, so the steps ran on every PR at the time of this change; the new unfiltered `count-ratchet-guard` job runs them in a job of their own | RESOLVED, issue #5636, PR #6060 (step 1: job added, old steps kept) and the step 2 PR (job name pinned in `REQUIRED_CONTEXTS`, duplicate steps deleted from `test`). Owner step left: add the same context to ruleset 11104075 | n/a | n/a |
| `agent-drift-detection.yml:79` | `validate` | `build/generate_agents.py --validate` | the filter is a strict subset of the audited filter that `validate-generated-agents.yml` uses for the identical command. Missing `docs/agent-catalog.md`, `.claude/**`, `.github/agents/**`, `.github/instructions/**`, `.github/prompts/**`, and `.github/workflows/**`, so a change to only those triggers the sibling workflow and not this one | A: widen the filter. Fixed in #6042. | rjmurillo | fixed in #6042 |
| `memory-health.yml` | `health-check` | `memory_enhancement health`, whole `.serena/memories/` tree then `verify_all_citations` | citations point at arbitrary target files anywhere in the repository. A change to a cited target outside `.serena/memories/**` and outside `scripts/**/*.py` does not trip the filter, so a citation staled by that change goes unverified | RESOLVED, issue #5636, PR #6061: filter now covers the ADR directory a citation resolves under. A file or function citation resolves to any repo path, so a test fails when a cited target falls outside the filter; the corpus cites none today | n/a | n/a |
| `memory-validation.yml:38` | `validate-memories` | `memory_enhancement verify-all` | RESOLVED by deletion, issue #5626; the same gap survives in the two rows above and below | RESOLVED by deletion, issue #5626 | n/a | n/a |
| `citation-verify.yml` | `verify-citations` | `memory_enhancement verify-all` | the same gap, closed the same way. The filter also gains `scripts/**/*.py`, matching memory-health | RESOLVED, issue #5636, PR #6061: see the memory-health row | n/a | n/a |

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

Assigned 2026-09-29. Issue #5636 requires an owner and a review date per entry.
Every non-resolved row names `rjmurillo` as owner, the repository owner, because
no row names another. The classes:

| Class | Rule | Expiry |
|---|---|---|
| `A` | Fail closed now. A required gate that passes without running is a false green (issue #5738, security.md MUST 7). Fixed in the PR named in the row. | the fixing PR |
| `B` | Keep non-blocking. The path is advisory, informational, not applicable, or already re-asserted downstream. Each row says why. | 2026-12-31, when the row is re-read |
| `C` | Needs an owner policy call: hardening would block real work today, or the design is open. Not decided in this file. | 2026-10-31, the date the decision is due |
| `RESOLVED` | The construct no longer exists or was already fixed. | n/a |

Counts on 2026-09-29, 72 classified rows: `A` 4, `B` 47, `C` 10, `RESOLVED` 11.

Update 2026-10-01: owner decision D24 (issue #5636) moved the two canonical-citation rows to `A`, hardened by the count ratchet in PR #6058. The counts above are not recomputed.

A `B` row that reaches its expiry without a re-read is a defect in this file,
not permission to keep the path open. Validate Spec Coverage currently fails
closed because the Copilot quota is exhausted, so no row whose hardening would
make that check blocking was classified `A`.

Line numbers in the Path column were read at `16ed125`. The class of each
row was re-checked against `b0e96997f` by searching the workflow tree for the
construct, and one row (`skill-passive-compliance.yml:90`) no longer exists
there.

## Keeping this file honest

This inventory is prose, and prose rots. Three specific ways it will drift:

1. A new `continue-on-error: true` lands in a workflow and nobody adds a row. Closed for this construct and for `SKIP_` toggles since decision D17: `check_bypass_allowlist.py` fails on an unlisted use, so the new one needs an allowlist entry with an owner and an expiry. It does not find a `|| true`, a toggle without `SKIP_` in its name, or a toggle assembled at run time.
2. A path listed here is hardened, and the row still says it fails open.
3. A cited line number moves and the citation silently points at the wrong code.

Nothing in this file detects the second and third, and the first is detected only for the constructs named above. That is a real gap and it is
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
