---
type: requirement
id: REQ-047
title: Gate pull requests on a real-CLI smoke for Claude, Copilot, and Codex, and move ai-review off Copilot
status: draft
priority: P1
category: functional
source: issue-6069
related:
  - ADR-114
  - ADR-071
  - REQ-037
created: 2026-10-08
updated: 2026-10-08
author: spec
tags:
  - ci
  - smoke
  - copilot
  - codex
---

# REQ-047: PR-gated CLI smoke and Copilot token retirement

## Step 0 First Principles

### Q1

The owner, in issue #6069 and in decisions D20 to D25 (ADR-114 debate log round 5). Agents that run `set_pr_auto_merge.py` are blocked by an always-red check. Issue #5738 names the same failure.

### Q2

The owner reads a red Validate Spec Coverage on every PR and ignores it. The nightly CLI smoke runs, fails, and nobody reads it. Plugin load breakage is found by hand.

### Q3

The owner. They cannot tell from a PR whether the plugin, hooks, and skills still load in each CLI. The nightly smoke failed on 2026-10-06 and 2026-10-07, and nobody acted.

### Q4

Move three `ai-review` callers to Claude. Turn the nightly smoke into a path-filtered PR check. Add a Codex leg. Share one path list between lefthook and CI. About 12 hours human, 2 hours AI-assisted.

### Q5

`gh run list --workflow nightly-cli-smoke.yml`: failure on 2026-10-06 and 2026-10-07. `ai-metrics-analysis.yml` and `artifact-insight-scanner.yml`: failure on 2026-09-21, 2026-09-28, and 2026-10-05. `pr-maintenance.yml`: last run failed on 2026-08-16. Issue #6069 Q5 lists seven PRs with a red Validate Spec Coverage on 2026-09-29.

### Q6

At 10x more PRs, the path filter keeps cost tied to plugin and smoke-harness changes, not PR count. Dependency updates to `pyproject.toml` or `uv.lock` also trigger it. Approval clicks grow with plugin PRs. That cost is the owner's choice (D21).

## Prior art (Step 0.5)

- PR #6150 moved Validate Spec Coverage to Claude. It added `provider: claude` to `.github/actions/ai-review/action.yml`.
- PR #6131 and PR #6197 put every model job behind a per-provider environment with required reviewers (ADR-114).
- `lefthook.yml` `hook-anchoring-e2e` and `plugin-load-e2e` already run both smokes on pre-push. The glob lists are duplicated in `scripts/validation/git_hook_policy.py` `_handle_cli_hook_e2e` and `_handle_cli_plugin_e2e`.
- ADR-114 Decision 8 says agent checks never block. This spec makes the CLI smoke the one exception, by owner decision D22 (ADR-114 debate log round 5).

## Problem statement

Copilot tokens are not funded for model review, but three workflows still call Copilot for it. The only proof that the plugin loads in each CLI runs nightly, and nobody reads it.

## User stories

1. As the owner, when I open a PR that changes plugin-shipped files, I see one smoke check that blocks merge until Claude, Copilot, and Codex each load the plugin.
2. As the owner, when a PR touches no plugin-shipped file, the smoke check passes without a model call or an approval click.
3. As a contributor in any harness, my pre-push hook runs the same smoke over the same path list, for each CLI I have installed.
4. As the owner, no job spends model tokens without my approval.

## Ontology

- **CLI smoke**: the pytest suites `tests/e2e/test_cli_hook_e2e.py` and `tests/e2e/test_plugin_load_smoke.py`, marked `smoke`, selected per CLI marker.
- **Leg**: one CLI on one OS. Three CLIs times three OS make nine legs.
- **Smoke path list**: the globs that decide whether a change can affect plugin loading or the smoke harness itself (the gate scripts, `pyproject.toml`, `uv.lock`). One Python source.
- **Provider environment**: `agent-claude` and `agent-copilot`. Each has a required reviewer and holds one provider's key. The Codex leg reads no key, so it needs no environment.
- **Smoke result**: the always-run job whose conclusion is the PR gate.

## Data model

No persisted data. The smoke path list is a Python tuple. Each leg emits a JUnit report that `assert_smoke_ran.py` reads.

## Integrations

| System | Use | Failure mode |
|---|---|---|
| Anthropic | Claude CLI leg (`CLAUDE_CODE_OAUTH_TOKEN`), `ai-review` provider `claude` (`ANTHROPIC_API_KEY`) | Missing key: smoke leg red, `ai-review` reports `infrastructure_failure` |
| GitHub Copilot | Copilot CLI leg only | `skill list` needs no quota. Prompt checks skip with a quota marker when quota is spent (D25) |
| Codex CLI | Codex leg: `plugin marketplace add`, `plugin add`, `debug prompt-input` | No credential needed; these commands make no model call |
| GitHub environments | Approval before each leg | Rejected or timed out: leg not run, smoke result red |

## Failure modes

- A plugin-shipped path is missing from the list. The smoke skips on a PR that needed it. Mitigation: the list lives in one module, and a test asserts lefthook globs equal it.
- A fork PR gets no secrets. The legs cannot run. The smoke result fails closed with a message naming the cause.
- A skipped pytest reads as a pass. `assert_smoke_ran.py` already fails a leg when nothing ran.
- An approval never comes. The smoke result stays red, and the PR does not merge. This is intended.

## Security

- Secrets reach only legs in their provider environment. Each leg reads one key.
- The trusted-context gate accepts `pull_request` only when the head repository equals the base repository.
- Same-repo writers can still edit the workflow on a branch. ADR-114 Decision 10 already records that residual.
- Actions stay pinned to 40-hex SHAs.

## Observability

The `changes` job prints which changed paths matched the filter. The result job prints one line: no smoke path changed, passed (with the count of quota-skipped prompt checks), or the failing job with its cause and next action. Each leg posts a `::notice::` for its quota skips. Success metric: no PR that touches a smoke path merges without a green smoke result.

## Acceptance criteria

1. WHEN `ai-metrics-analysis.yml`, `artifact-insight-scanner.yml`, or `pr-maintenance.yml` calls `ai-review`, the call SHALL pass `ANTHROPIC_API_KEY` to the Claude-only action, and run in `agent-claude`.
2. The `ai-review` action SHALL NOT read `COPILOT_GITHUB_TOKEN` or install the Copilot CLI. Its Copilot-only inputs, steps, and scripts with no remaining caller SHALL be removed.
3. The only workflow that reads `COPILOT_GITHUB_TOKEN` SHALL be the CLI smoke, on its Copilot legs, in `agent-copilot`.
4. WHEN a pull request changes a file in the smoke path list, the CLI smoke SHALL run Claude, Copilot, and Codex legs on Ubuntu, macOS, and Windows.
5. WHEN a pull request changes no file in the smoke path list, the smoke result SHALL pass with no leg run and no model call.
6. The smoke result SHALL fail WHEN any leg that should run fails, is skipped, is cancelled, or never gets approval.
7. The plugin CLI smoke workflow (`plugin-cli-smoke.yml`; `cli-smoke.yml` is the unrelated bun CLI smoke) SHALL NOT be listed in `advisory_agent_workflows`, so its failure blocks merge.
8. `nightly-cli-smoke.yml` SHALL be removed. Live references SHALL point at the PR workflow.
9. Each job that reads a model key SHALL declare the matching provider environment. The existing test SHALL cover the new workflow and the Codex legs.
10. The pre-push hooks and the CI path filter SHALL read one smoke path list. A test SHALL fail WHEN `lefthook.yml` globs differ from it.
11. A Codex smoke SHALL install `project-toolkit@ai-agents` from `.claude-plugin/marketplace.json` into an isolated `CODEX_HOME`, assert the installed entry, and assert every `EXPECTED_SKILLS` name appears as `project-toolkit:<name>` in `codex debug prompt-input`. It SHALL read no credential and run in no provider environment.
12. WHEN a fork PR touches a smoke path, the smoke result SHALL fail and name the fork as the reason.

13. The Copilot leg SHALL prove skill load with no model call: `copilot --plugin-dir src/copilot-cli skill list --json` from a neutral directory lists every `EXPECTED_SKILLS` name with a path under `src/copilot-cli`, and no loader warning. This check SHALL never skip.
14. WHEN a Claude or Copilot prompt-based check is blocked by an exhausted quota or credit balance, it SHALL skip with a stable marker, and the gate SHALL report it without failing (owner decisions D25 and D26, ADR-114 debate log round 5). Auth failures, Copilot rate limits, and any other skip SHALL fail the leg. A Claude 429 counts as exhausted quota, because the Claude CLI reports both limits the same way. Each leg's zero-token load check SHALL pass, never skip. Codex stays strict.
15. The path filter, trusted-context gate, skip gate, and result reporter SHALL execute from the pull request base commit, so a pull request cannot change the scripts that judge it. The workflow YAML comes from the pull request head, and review of its diff is the control.
16. WHEN a moved `ai-review` job runs with an unfunded `ANTHROPIC_API_KEY`, it SHALL report an infrastructure failure and SHALL NOT block any merge (D26).

## Out of scope

- Adding the smoke result to the branch ruleset. The owner does that in repository settings.
- Codex hooks and agents. `src/claude/hooks.json` ships no hooks, and Codex exposes no agents key for plugins.
- `copilot-context-synthesis.yml`. It assigns the Copilot coding agent and is already gated in `agent-copilot`.

## Deferred

- Removing eval harness Copilot code under `scripts/eval/`. Owner: rjmurillo.

## Open questions

- None. Codex research (2026-10-08, codex-cli 0.161.0): Codex reads `.claude-plugin/marketplace.json` and `src/claude/.claude-plugin/plugin.json` as-is. `skills/list` and `debug prompt-input` show all 110 skills with no model call.

## CVA summary

- Common: each leg installs a pinned CLI, installs the plugin from the repo, runs marked pytest, and asserts the smoke ran.
- Varies: CLI package, credential name, provider environment, plugin directory, and install command.
- Relationship: the matrix `cli` value selects all variable parts, so a leg is one row of data.

## Buy-vs-build decision

N/A (CI refactor). The build reuses the existing smoke suites and `assert_smoke_ran.py`. It adds three small stdlib scripts: `cli_smoke_paths.py` (path filter), `smoke_result.py` (result reporter), and `smoke_quota_report.py` (quota-skip notices and counts).

## Complexity classification

Tier 3. Domain: Complicated. Method: plan, then thin vertical slices with tests.
