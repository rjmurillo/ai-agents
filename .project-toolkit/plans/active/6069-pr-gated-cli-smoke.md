# Execution Plan: PR-gated CLI smoke and Copilot token retirement

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-10-08 |
| **Owner** | claude (plan skill) |
| **Complexity** | High |

## Objectives

- [ ] M1: The three `ai-review` callers run on Claude in `agent-claude`, and the action has no Copilot path (REQ-047 AC1, AC2, AC3).
- [ ] M2: One smoke path list feeds lefthook and CI (AC10).
- [ ] M3: A Codex plugin-load smoke exists and needs no credential (AC11).
- [ ] M4: `plugin-cli-smoke.yml` gates PRs, and the nightly is gone (AC4 to AC9, AC12).
- [ ] M5: ADR-114, ADR-071, docs, and generated mirrors match the new state.

## Milestones and tasks

### M1: Move ai-review off Copilot

Exit: `git grep COPILOT_GITHUB_TOKEN -- .github` shows only the Copilot smoke legs. Unit tests pass.

| Task | Size | Done when |
|------|------|-----------|
| T1.1 Switch `ai-metrics-analysis.yml`, `artifact-insight-scanner.yml`, `pr-maintenance.yml` to `provider: claude`, `anthropic-api-key`, `environment: agent-claude`. Drop `copilot-token` and `copilot-model`. | S | Three files updated, provider-environment test passes |
| T1.2 Remove the Copilot install, diagnose, and invoke steps, plus their inputs and outputs, from `.github/actions/ai-review/action.yml`. Claude becomes the only provider. Drop `provider:` from `ai-spec-validation.yml`. | M | Action has no `copilot` step or input. Output names consumers read still resolve |
| T1.3 Delete scripts and tests that lose their last caller (candidates: `install_copilot_cli.py`, `diagnose_copilot_cli.py`, `verify_github_auth.py`, `_copilot_model.py`). Keep anything `invoke_claude_review.py` or `scripts/eval` imports. | M | `git grep` shows no reference to a deleted module |
| T1.4 Update the tests that pin the action shape. | M | `pytest tests/ci tests/test_*ai_review*` green |

### M2: One smoke path list

Exit: lefthook globs and `git_hook_policy.py` read one module. A test fails on drift.

| Task | Size | Done when |
|------|------|-----------|
| T2.1 Add `scripts/validation/cli_smoke_paths.py` holding the hook and plugin glob tuples. Add `.claude-plugin/marketplace.json` and `src/claude/**`. Point at `plugin-cli-smoke.yml`. | S | Module imported by `git_hook_policy.py` |
| T2.2 Add a CLI entry that takes changed paths and prints `run=true` or `run=false`, for CI. | S | Unit tests cover match, no match, empty list |
| T2.3 Add a test that lefthook `hook-anchoring-e2e` and `plugin-load-e2e` globs equal the module tuples. | S | Test fails when one glob is removed |
| T2.4 Local gate: accept `codex` as a third CLI in `run_cli_e2e`. | S | Unit test for the three-CLI check |

### M3: Codex smoke

Exit: `RUN_CLI_E2E=1 uv run pytest tests/e2e/test_plugin_load_smoke.py -m "smoke and codex"` passes locally with codex-cli 0.161.0.

| Task | Size | Done when |
|------|------|-----------|
| T3.1 Register the `codex` marker in `pyproject.toml`. Add `requires_codex`. | S | Marker listed |
| T3.2 Add `test_codex_plugin_loads_expected_skills`. Use an isolated `CODEX_HOME`, `plugin marketplace add`, `plugin add project-toolkit@ai-agents`, `plugin list --json`, and `debug prompt-input`. Assert every `EXPECTED_SKILLS` name appears as `project-toolkit:<name>`. | M | Passes locally. A negative unit test for the parser |

### M4: PR-gated workflow

Exit: a `workflow_dispatch` run of `plugin-cli-smoke.yml` on this branch passes every leg (the branch head is the trusted base on dispatch). This PR's own `pull_request` run is red by design, because `main` lacks the base-commit gate scripts (ADR-114 Decision 13.1). After merge, a dispatch on `main` must pass before the owner makes the check required.

| Task | Size | Done when |
|------|------|-----------|
| T4.1 Extend `assert_trusted_smoke_context.py` to accept `pull_request` when the head repository equals the repository. | S | Tests cover same-repo, fork, and unknown event |
| T4.2 Write `.github/workflows/plugin-cli-smoke.yml`: `changes`, `authorize`, `smoke` (claude and copilot by three OS, `agent-${{ matrix.cli }}`), `smoke-codex` (three OS, no environment, no secret), `smoke-result` (always). Claude legs read `CLAUDE_CODE_OAUTH_TOKEN`. Copilot legs read `COPILOT_GITHUB_TOKEN`. Pin the Codex CLI with a renovate comment. | L | actionlint clean. Security test passes |
| T4.3 Delete `nightly-cli-smoke.yml`. Rename and update `tests/test_nightly_cli_smoke_security.py`. | M | No live reference to the nightly |
| T4.4 Update `tests/test_pr_merge_ready_advisory_agent_checks.py`: name `plugin-cli-smoke.yml` as the one blocking gated workflow, with a reason. Update `EXPECTED_JOB_ENVIRONMENTS`. | S | Tests green |

### M5: Records and docs

| Task | Size | Done when |
|------|------|-----------|
| T5.1 Amend ADR-114 (Decision 2 table, new Decision 13, nightly rows) and add dated amendments to ADR-071, ADR-083, ADR-094. Add a debate-log round. | M | Reduced panel finds no open P0 or P1 |
| T5.2 Update `templates/rules/generated-artifacts.md`, skill templates, `CONTRIBUTING.md`, `docs/COST-GOVERNANCE.md`, `renovate.json`. Run `build_all.py`. | M | Mirrors match. Build check green |
| T5.3 Mark REQ-047 `implemented`. | S | Frontmatter updated |

## Dependency graph

- M1 is independent of M2 to M4.
- M2 blocks M4 (T4.2 calls the path module).
- M3 blocks T4.2 (the Codex job runs the new test).
- M5 runs last.
- M1 and M2 plus M3 can run in parallel.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `ANTHROPIC_API_KEY` has no credit (10-07 nightly: "Credit balance is too low") | High | `ai-review` jobs report infra failure | Owner action in PR body. The smoke legs use `CLAUDE_CODE_OAUTH_TOKEN` instead |
| A shipped path is missing from the filter | Medium | Smoke skips a breaking PR | One module, drift test, and broad globs (`src/claude/**`, `src/copilot-cli/**`) |
| The smoke result is not a required check in the ruleset | High | GitHub auto-merge ignores it | Owner action. `pr_merge_ready` already blocks on non-advisory failures |
| Copilot legs skipped on 10-07 (hook probe) | Medium | Copilot legs red on this PR | Run Copilot smoke locally before push. Fix or report with evidence |
| Codex CLI version drift changes `debug prompt-input` | Low | Codex leg red | Pin the version, and renovate bumps it through this same gate |
| Fork PR touching smoke paths | Low | Fork cannot merge without help | Fail closed with a message. A maintainer reruns from a same-repo branch |

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-10-08 | D20: move ai-review off Copilot | Owner decision on #6069 | Reconcile only |
| 2026-10-08 | D21: keep the Copilot CLI smoke; every token-spending job behind approval | Owner needs proof skills load | Full retirement |
| 2026-10-08 | D22: path-filtered PR gate | Owner: nobody checks nightlies | Every PR |
| 2026-10-08 | D23: full three-OS matrix, nightly removed | Windows bugs #2205 and #3324 | Ubuntu and Windows only |
| 2026-10-08 | D24: Codex leg now | Owner: same gates for Claude and Codex | Follow-up issue |
| 2026-10-08 | Claude smoke legs use `CLAUDE_CODE_OAUTH_TOKEN` | Subscription cost. API key out of credit on 10-07 | `ANTHROPIC_API_KEY` |
| 2026-10-08 | Planning subagents skipped; milestones and pre-mortem written inline | A session subagent cap was in force. The owner removed that cap later the same day. Review uses separate agents and the full ADR panel | Four planning subagents |
| 2026-10-08 | Workflow named `plugin-cli-smoke.yml` | `cli-smoke.yml` is the existing bun CLI smoke | Rename the bun smoke |
| 2026-10-08 | D25: Copilot gate is zero-token; prompt checks best-effort | Copilot quota is spent locally (HTTP 402) and unfunded in CI | Strict, or drop prompt checks |
| 2026-10-08 | D26: budget exhaustion is an accepted gap for every provider; auth still fails | Owner: keys will not always be funded | Fund every key; strict legs |
| 2026-10-08 | Path filter runs from the base commit | A pull request must not edit the filter that gates it | Run from the head checkout |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-10-08 | Created plan | claude |
| 2026-10-08 | Review fixes: smoke_result.py and smoke_quota_report.py split out at 5b339a526 | implementer |
| 2026-10-08 | M1 to M4 committed (e6538bdf2, 262070379, c236a60ab, 1fa987732) | implementer |

## Blockers

- None

## Related

- Issue: #6069, #5738
- Spec: `.project-toolkit/specs/requirements/REQ-047-pr-gated-cli-smoke-and-copilot-token-retirement.md`
- ADR: ADR-114, ADR-071
