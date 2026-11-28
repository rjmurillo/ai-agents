# ADR-104 Amendment 2026-11-27: Claims Ledger

Scope: `## Amendment 2026-11-27: Retire CI-Owned Heavy Passes From Pre-Push`,
the rule 2 rewrite, the Consequences compute-lane line, and the four Impact
rows dated 2026-11-27 in
`.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md`.
Tree: branch `t3/audit-remove-heavy-local-hooks`, first pass at `507754b326`,
round 1 fixes at `e788140223`, plus the uncommitted ADR, 2026-11-27. Results
read from the working tree. Rows 3, 10 to 13 and 28 are in-session runs at
earlier commits; the hook config they measure is unchanged since.

| # | Claim | Kind | Command | Result |
|---|---|---|---|---|
| 1 | `pre-push` has 25 leaf jobs; `plugin-scanner` and `count-ratchets` are absent | count | `yaml.safe_load(lefthook.yml)`, walk `pre-push.jobs` groups | VERIFIED: 25 names, neither job present |
| 2 | 13 jobs are container-unclamped, 12 clamped | count | read `CONTAINER_UNCLAMPED_JOBS` in `scripts/ci/lefthook_budget_model.py:61-77` | VERIFIED: 13 entries, `plugin-scanner` absent; 25 - 13 = 12 |
| 3 | Declared pre-push total stays 3330s | count | `tests/ci/test_lefthook_declared_budget.py` (targeted run, 2026-11-27) | VERIFIED: passed at `7eae0095e2`; no cap changed since |
| 4 | `workflow-local-run` cap is 30m and sets the outer group | behavior | `lefthook.yml` job `workflow-local-run` | VERIFIED: `timeout: 30m` |
| 5 | `_Gate.ci_owned_by` and `REASON_CI_OWNED = "policy.ci_owned"` exist | path | `grep -n ci_owned_by scripts/validation/pre_pr_sequence.py`; `grep -n REASON_CI_OWNED scripts/validation/evidence.py` | VERIFIED: gate rows at 340-346 and 528; constant exported |
| 6 | The skip fires only when `AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1` and prints under `--compact` | behavior | `scripts/validation/pre_pr_sequence.py:912` (`if fast_stage_ran and gate.ci_owned_by`); `tests/validation/test_pre_pr_sequence_registry.py::TestFastStageDeferral`; `tests/validation/test_pre_pr_compact.py` | VERIFIED: tests pass; `REASON_CI_OWNED` is not in the quiet set |
| 7 | `count-ratchets` standalone: 30.3s wall, 110.0s CPU | count | `time uv run --frozen python scripts/validation/git_hook_policy.py count-ratchets`, load1 5.1 | VERIFIED: `real 30.315 user 88.113 sys 21.880`, rc=0 |
| 8 | `plugin-scanner` standalone: 56.5s wall, 56.5s CPU | count | `time uv run --frozen python scripts/validation/check_plugin_scanner_score.py`, load1 6.6 | VERIFIED: `real 56.500 user 45.218 sys 11.238`, rc=0 |
| 9 | `build_all.py --check`: 13.2s wall and CPU, exit 2 on the uncommitted ADR index | count | `time uv run --frozen python build/scripts/build_all.py --check` | VERIFIED: `real 13.159 user 11.612 sys 1.622`, rc=2, `STALE-generated: [adr-index]` |
| 10 | Baseline push waited 420s for a heavy slot, then failed `security-scan` | behavior | `.project-toolkit/scratch/hook_before.log` | VERIFIED: `real 7m23.058s`, `user 0m27.941s` |
| 11 | Before: 245.9s wall, 509.4s CPU, load1 18.3, 1 file, `security-scan` excluded | count | `.project-toolkit/scratch/hook_before2.log` | VERIFIED: `real 4m5.927s user 6m52.728s sys 1m36.720s`, load 18.31 |
| 12 | After: 167.6s wall, 308.6s CPU, load1 4.8, 36 files, `push-ref-policy` also excluded | count | `.project-toolkit/scratch/hook_after2.log` | VERIFIED in session at `7eae0095e2`; not re-run at this head |
| 13 | `semgrep-core` exits -11 under an 8 MiB stack; `ulimit -s unlimited` clears it | behavior | `git_hook_policy.py semgrep-push` under both limits | VERIFIED: rc -11 vs rc 0 |
| 14 | `RATCHETS` has 10 scripts; the CI owners run all 10 | count | `from checks_ratchet import RATCHETS`; `tests/validation/test_pre_pr_ci_owned_gates.py::test_count_ratchets_owners_are_exactly_the_jobs_that_run_the_registry` | VERIFIED: 10 scripts; test passes |
| 15 | No owner job has a job-level `if:` | behavior | `yaml.safe_load` on `pytest.yml`, `pr-validation.yml`, `plugin-scanner.yml`, `validate-generated-agents.yml` | VERIFIED: `count-ratchet-guard`, `test`, `validate-pr`, `scan`, `build-all-staleness` all `if=None` |
| 16 | Among steps that run a ratchet script, the one step-level condition is `matrix.primary` on `ruff_ratchet.py` | behavior | `sed -n '418,428p' .github/workflows/pytest.yml`; `ALLOWED_STEP_IF` in `tests/ci/ratchet_test_helpers.py:46`, enforced at 126 | VERIFIED after correction: the first draft said "the one step-level condition" in the job; `pytest.yml` has 11 `if: matrix.primary` steps (refuting seat) |
| 17 | Trigger sets per owner workflow | behavior | `on:` blocks of the four workflows | VERIFIED: pytest and validate-generated: push, PR, merge group on main, dispatch; pr-validation: PR and merge group on main; plugin-scanner: push and PR on main, dispatch |
| 18 | Required contexts include "Check whole-tree count ratchets (blocking)", "Run Python Tests", "Validate Generated Files", "Validate PR"; Plugin Scanner is absent | absence | `grep -n '"' scripts/ci/ruleset_required_contexts.py`; `grep -rn "Plugin Scanner" scripts/ci/ruleset_required_contexts.py` | VERIFIED: four present; no Plugin Scanner entry |
| 19 | "Run Python Tests" is the `test-result` rollup, which needs `test` | behavior | `pytest.yml:1049` (name), `:1050-1051` (`needs:` with `test`) | VERIFIED |
| 20 | "Validate Generated Files" needs `build-all-staleness` | behavior | `validate-generated-agents.yml:119,125` | VERIFIED |
| 21 | `workflow-local-run` runs changed workflows under `act`, including schedule-only and dispatch-only ones | behavior | `scripts/validation/git_hook_policy.py:567` (scope); `scripts/validation/run_workflow_local_test.py:990-1000` (event names incl. `schedule`, `workflow_dispatch`) and `:1326` `_select_act_event` | VERIFIED after correction: first draft cited `git_hook_policy.py:990-1000` (refuting seat) |
| 22 | `agent-metrics.yml` triggers on schedule and dispatch only; jobs `collect-metrics`, `check-thresholds` | behavior | `grep -n '^on:\|schedule\|workflow_dispatch\|pull_request' .github/workflows/agent-metrics.yml`; job keys | VERIFIED |
| 23 | No workflow runs Semgrep; one file names it in a comment | absence | `grep -rln semgrep .github/workflows/` (whole directory) | VERIFIED at `f8398e1b2d` (2026-11-27): `ai-spec-validation.yml:43`, a comment; `ai-spec-review.yml` was deleted by #7654 |
| 24 | No workflow runs `test_cli_hook_e2e.py`; `test_plugin_load_smoke.py` runs in CI only with `-m "smoke and codex"` | absence | `grep -rn 'test_cli_hook_e2e\|test_plugin_load_smoke' .github/workflows/` (whole directory) | VERIFIED at `f8398e1b2d` (2026-11-27): only `plugin-cli-smoke.yml:230,240` (codex leg); #7654 deleted the `smoke` job that held lines 290-347 |
| 25 | No workflow runs `pre_pr.py` | absence | `grep -rn 'pre_pr.py' .github/workflows/` | VERIFIED: comments only (for example `pr-validation.yml` rule-scope step) |
| 26 | `rule-ci-scripts.md` heading "Path filters gate the diff, never the tree" | quote | `grep -rn` | VERIFIED: `.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md:100` |
| 27 | Heavy-stage slots live in `scripts/validation/host_headroom.py` | path | `grep -n heavy scripts/validation/host_headroom.py` | VERIFIED: line 1 docstring, slot dir line 115 |
| 28 | Revert base `d31aa71e60` holds the two jobs | path | `git show d31aa71e60:lefthook.yml \| grep -n 'name: plugin-scanner\|name: count-ratchets'` | VERIFIED in session before removal |
| 29 | On-demand `count-ratchets` found a 534-line test file (taste 436 > 435) | behavior | `git_hook_policy.py count-ratchets` at `54bcb5cbae` | VERIFIED: fixed in `507754b326`; rerun rc=0 |
| 30 | A direct run of `pre_pr.py` executes both CI-owned gates; no CI run exists | behavior | `pre_pr_sequence.py:912` gate on `fast_stage_ran`; row 25 | VERIFIED after correction: first draft said "Direct and CI runs" (doc-accuracy) |
| 31 | The remaining `plugin-cli-smoke.yml` legs cover Claude hook discovery, Codex, and Pi | behavior | job keys `smoke-codex`, `smoke-claude-hooks`, `smoke-pi`; `:312` runs `test_claude_hook_discovery_smoke.py` | VERIFIED at `f8398e1b2d` (2026-11-27), re-checked after #7654 removed `smoke` |
| 32 | Scanner scored 80 against a minimum of 80 on 2026-11-27 | count | `.project-toolkit/scratch/scanner_before.log` | VERIFIED: `score=80 min=80 margin=0` |
| 33 | Scanner findings include "No privileged untrusted checkout patterns" | quote | `check_plugin_scanner_score.py` run output, 2026-11-27 | VERIFIED: `-5 [codex:.] Repository Operational Security: No privileged untrusted checkout patterns` |
| 34 | PR #5418 consolidated ratchets into pre-push; PR #6913 added the scanner job | path | `git log -S'name: count-ratchets' -- lefthook.yml`; `git log -S'name: plugin-scanner' -- lefthook.yml` | VERIFIED: `4e33c4baa0` 2026-08-29 (#5418); `fa1d7c52c2` 2026-10-24 (#6913) |
| 35 | Ownership tests reject a `paths` filter on an owner workflow | behavior | `uv run pytest tests/validation/test_pre_pr_ci_owned_gates.py` | VERIFIED: 16 passed, incl. `filtered.yml` negative control |
| 36 | CI ratchets answer the same two questions as the local gate: merge base (standalone) and base tip (merge-tree) | behavior | `pr-validation.yml:284-295` (`--base-ref FETCH_HEAD`, the base tip; `base_derived_ratchet.py` derives the merge base from it), `:428` merge-tree; `checks_ratchet.py:36-47` | VERIFIED: the analyst seat's round 1 claim that CI uses the base tip only was wrong |
| 37 | ADR is under 1000 lines | count | `wc -l` | VERIFIED: 977 |

## Exit Gates

| Gate | Result | Notes |
|---|---|---|
| 1. Claims ledger | VERIFIED | 37 rows; absence rows 18, 23, 25 searched the whole `.github/workflows/` or file |
| 2. Documentation accuracy (Phase 4, Sonnet) | VERIFIED after fixes | 2 low findings: "Direct and CI runs" contradiction; e2e row implied no PR-time coverage. Both fixed (rows 30, 31). 215s |
| 3. Self-consistency | VERIFIED | Binding changes 1-3, rule 2, rule 3 non-conformance list, Consequences agree. Fixed "four kept" to "five kept" |
| 4. Refuting seat (analyst, Haiku) | VERIFIED after fixes | 2 refuted (rows 16, 21), 1 off-by-one (row 19); all corrected. Rows 3, 7-13, 28, 29 UNAVAILABLE to a read-only seat. 218s |
| 5. ADR review hand-off | VERIFIED | Ledger path recorded in `.project-toolkit/critique/ADR-104-ci-owned-heavy-passes-debate-log.md` before round 1 findings |
