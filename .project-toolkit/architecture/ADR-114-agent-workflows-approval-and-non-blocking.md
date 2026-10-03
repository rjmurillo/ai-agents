---
id: ADR-114
status: proposed
date: 2026-10-03
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-04-03
---

# ADR-114: Agent Workflows Run Only After Approval and Never Block Merges

## Context

Ten workflows call a model or an agent, and they start on pull request events, schedules, issue labels, or dispatch with no person in the loop. The readiness check also lets their results hold a merge: `test_pr_merge_ready.py` blocks a failed non-required check that has no disposition (issue #4902), and with `--include-non-required` it blocks a waiting or pending one too. The owner set the policy that no agent workflow starts without approval and none blocks a merge (decisions D4, D6, D8 to D12), and ADR-057 says the `/spec` eval is a blocking CI leg, which conflicts with it.

## Decision

1. **Approval before running.** Every job that calls a model declares `environment: agent-approval`. The environment is meant to carry required reviewers, so a run waits for a reviewer before the job starts. A job takes one environment, so these jobs swap `environment: bot-secrets` for `agent-approval`. The `bot-secrets` environment holds 0 secrets and 0 variables (Environments API, 2026-10-02), so the swap moves no secret or variable. A comment in `ai-spec-validation.yml` once said the job "holds an environment secret". That comment predated the API check and was stale, and this change rewords it.

2. **Ten workflows are in scope.** Gated jobs:

   | Workflow | Gated job | Model call |
   |----------|-----------|------------|
   | `ai-spec-validation.yml` | `validate-spec` | `.github/actions/ai-review` |
   | `slash-command-quality.yml` | `validate-slash-commands` | `ANTHROPIC_API_KEY`, `scripts/eval/eval-prompt-change.py` |
   | `post-pr-retrospective.yml` | `retrospective` | `anthropics/claude-code-action` |
   | `software-engineering-library-activation.yml` | `activation-gate` | `ANTHROPIC_API_KEY` |
   | `ai-metrics-analysis.yml` | `analyze-metrics` | `.github/actions/ai-review` |
   | `pr-maintenance.yml` | `process-prs` | `.github/actions/ai-review` |
   | `artifact-insight-scanner.yml` | `scan-artifacts` | `.github/actions/ai-review` |
   | `skill-overlap-eval.yml` | `run-eval` | `ANTHROPIC_API_KEY` |
   | `nightly-cli-smoke.yml` | `smoke` (3 matrix legs) | steps "Run real-CLI hook smoke" and "Run real-CLI plugin-load smoke" run `claude -p` and `copilot -p` through `tests/e2e/test_cli_hook_e2e.py` and `tests/e2e/test_plugin_load_smoke.py` |
   | `copilot-context-synthesis.yml` | `synthesize-single`, `sweep-missed` | assigns the issue to the Copilot agent after synthesizing context |

   Jobs in those workflows that call no model keep their existing environment.

3. **`claude.yml` is excluded from approval.** It answers a human `@claude` mention or an assigned issue and already runs its own authorization check (`check-authorization`, `tests/workflows/test_claude_authorization.py`). An approval click per reply would defeat its interactive purpose. Its `claude-response` job moves from `bot-secrets` to `environment: agent-claude`, an environment with no required reviewers. It exists only to hold `CLAUDE_CODE_OAUTH_TOKEN` once the owner scopes the token to it. No other line of `claude.yml` changes.

4. **Checks are advisory, identified by workflow file.** A non-required check is exempt from blocking only when its CheckRun belongs to a listed workflow file. The identity is read from `checkSuite.workflowRun.workflow.resourcePath`, which maps to `.github/workflows/<file>`. The GraphQL `Workflow` type has no `path` field (introspected 2026-10-02: `createdAt`, `databaseId`, `id`, `name`, `resourcePath`, `runs`, `state`, `updatedAt`, `url`). A check name is free text any workflow can reuse, so a name list lets an unrelated check borrow a listed name. The resource path must also match the pull request's own repository. Both GraphQL queries select the field, including the pagination query, and a test pins that.

5. **The list is `advisory_agent_workflows` in `.claude/skills/pr-review/pr-review-config.yaml`.** Each entry has `path`, `reason`, and `owner` (`rjmurillo`). It holds the four workflows that trigger on `pull_request`: `ai-spec-validation.yml`, `slash-command-quality.yml`, `post-pr-retrospective.yml`, and `software-engineering-library-activation.yml`. The other six are gated but not listed. Their triggers are schedule, issue label, or dispatch only. A scheduled run attaches to the default branch and posts no check on a pull request. A `workflow_dispatch` run on a pull request branch is different: GitHub attaches check runs to the commit, so such a run is expected to appear in that pull request's rollup (expected from the commit-scoped check model, not observed here). If that run fails, its non-required check blocks until a disposition covers it. The owner chose the pruned list and accepts this residual. Trigger to revisit: the first dispatch of an unlisted agent workflow on a pull request branch.

6. **The list is read from the trusted ref.** `test_pr_merge_ready.py` runs `git show origin/main:<config>` and never reads the work tree, so a pull request that edits its copy cannot exempt its own failing check (CWE-829). When the ref or the list cannot be read (absent ref, shallow clone without the ref, parse error, no git), the reader returns an empty list and prints a stderr warning naming the reason. Empty means every check keeps its normal verdict. The reader skips the load when `ignore_ci` is set. The completion gate's criterion command names `test_pr_merge_ready.py`, so the gate byte-compares that script against the trusted ref before it runs (dispatched-file trust, ADR-059). A direct run of the script from a pull request tree, outside the gate, is not covered. Trigger to revisit: the first exemption-related incident.

7. **Precedence.** A check the branch ruleset requires stays blocking even when its workflow is listed. The reader uses GitHub's `isRequired` field. A StatusContext row has no workflow run, so it stays blocking. A name shared by a listed and an unlisted row is not exempt. `why_pr_blocked.py` reports required checks only and never reports a non-required one, so it already agrees with the exemption and needs no shared helper. A test pins both halves.

8. **Failed is non-blocking by design.** For a listed workflow, a check that is waiting, queued, pending, in progress, skipped, cancelled, timed out, or failed never blocks `CanMerge`. An agent verdict is advisory, and a reviewer reads it.

9. **`merge_group` leaves `ai-spec-validation.yml`.** Approval cannot happen inside a merge-queue run, and `validate-spec` was the only job the trigger fed. The `if:` term stays as a guard. The ADR-101 line references to this file (`:102`, `:97-102`) were already stale before this change: `always()` sits at line 82 on `main`.

10. **The gate is not a trust boundary.** ADR-101:261 states that a stanza on a job in a head-defined workflow contains nothing: the pull request can delete the stanza and request the repository-level secret directly. It also rejects an environment with required reviewers as the fix, because it reintroduces a human decision on every pull request. This ADR overrides that rejection for spend control only, by owner decision. The `agent-approval` environment is repository configuration, which is plane P2 in ADR-101. The `environment:` line in a workflow is P0 content a writer can edit. The gate binds only when the model secrets are scoped to the environment. Then a job that deletes the stanza receives no secret, and a job that keeps it waits for a reviewer.

11. **Owner actions before the policy is true.** Until they are done, automatic spend is not stopped. `ANTHROPIC_API_KEY` is a repository-level secret (Actions secrets API, 2026-10-02), so any job that references it runs without approval, with or without the stanza. `CLAUDE_CODE_OAUTH_TOKEN`, `BOT_PAT`, and `COPILOT_GITHUB_TOKEN` did not appear in the repository secret list, and organization-level secrets could not be listed with the available token (HTTP 404). Their scope is unverified, and the same bypass applies to any that is not environment-scoped. Required actions, in order:
    1. Create `agent-approval` in Settings > Environments with required reviewers and "prevent self-review". Record evidence (a screenshot or the Environments API output) in the pull request body.
    2. Create `agent-claude` with no reviewers.
    3. Move `ANTHROPIC_API_KEY` into `agent-approval` and `CLAUDE_CODE_OAUTH_TOKEN` into `agent-claude`. Delete the repository-level and organization-level copies.
    4. Split `BOT_PAT` into a model-only token for `ai-review` and the tokens that act on pull requests, so the approval gate guards the token that calls a model.

12. **An unprotected environment fails silently.** GitHub's documentation says a workflow that references a missing environment creates it with no protection (docs.github.com, "Managing environments for deployment"; not re-verified in this session). Then runs are unapproved and their checks still never block, so nothing signals the gap. Residual spend actors even when the environment is protected: a writer who edits a workflow on a branch, a writer who dispatches a workflow, and the `claude.yml` triggers, which run by design. As of 2026-10-02 the environments are `bot-secrets`, `copilot`, and `vendor-provenance`.

## Deferred Items

| Item | Why deferred | Trigger to revisit |
|------|--------------|--------------------|
| In-repo probe that `agent-approval` has required reviewers | Reading protection rules needs an admin-scoped token. CI has none. | An admin-scoped CI token exists. |
| Registry expiry for the list, and merging it into `dispositions.json` | Four entries with one owner do not need a registry. | The list exceeds 12 entries, or a second consumer of the list appears. |
| Detector for a listed workflow that gains a non-agent job | Review of the workflow diff is the control today. | The gap is accepted explicitly until a trigger below fires. |
| Split agent jobs into dedicated `agent-*.yml` files so a path means "agent only" | Granularity is per file, so a non-agent job added to a listed file becomes non-blocking. | A tenth PR-triggered agent workflow lands. |
| Named owner for dispatching the `/spec` eval on prompt-file diffs | Review is human-only until a regression shows the cost. | The first prompt regression found after merge. |

## Alternatives Considered

| Alternative | Pros | Cons | Verdict |
|-------------|------|------|---------|
| Bare check-name list | Simple to read and test | Any workflow can emit a check with a listed name | Rejected: spoofable |
| Add each check to `dispositions.json` | Reuses an existing registry with expiry | A disposition names a failed check, so waiting and pending checks still block with `--include-non-required`, and entries expire | Rejected for now |
| Keep checks blocking, gate only the start | No change to readiness logic | A run that waits for approval blocks every pull request until someone clicks | Rejected |
| Disable the workflows | No spend | Loses the advisory signal and the scheduled analyses | Rejected |
| Environment approval plus a workflow-path exemption read from the trusted ref | Approval before spend, no block, no spoof by name or branch edit | Needs an owner-maintained environment and environment-scoped secrets | Chosen |

## Prior Art Investigation

### What Currently Exists

- **Environment use:** 16 jobs named `environment: bot-secrets` on `main` before this change. No environment has a branch policy (ADR-101).
- **Non-required failure handling:** `_check_nonrequired_dispositions` in `test_pr_merge_ready.py` (issue #4902).
- **Config trust:** `run_completion_gate.py` byte-compares `pr-review-config.yaml` and each argv file against `origin/main` (ADR-059).

### Why Change Now

The owner set the policy. The readiness check cannot express "never blocks" without an exemption, and ADR-101:261 had rejected approval environments, so the override needs a record.

## Rationale

The exemption is keyed on the workflow file because a check name is free text and a workflow path is not. The list that names the path lives where the completion gate already verifies trust. A check from `pytest.yml` with the job name `Validate Spec Coverage` must still block, and a test pins that case.

Required precedence follows ADR-101: a required context is matched by name in the ruleset, so a listed workflow cannot lower a requirement. Failed is non-blocking because the policy treats every agent verdict as advisory.

## Consequences

### Positive

- With environment-scoped secrets, no model spend starts without a reviewer click.
- A model outage, a refusal, or a skipped run never holds a merge.
- A pull request cannot exempt its own failing check by editing the list.

### Negative

- Until the owner actions in Decision 11 are done, repository-level model secrets stay a bypass. This ADR does not claim automatic spend is stopped before then.
- Prompt regressions are no longer caught automatically before merge. The `/spec` eval runs only after approval. Review of prompt-file diffs is human-only, with no named owner for dispatching the eval, until the first prompt regression found after merge (ADR-057 Amendment 2026-10-02).
- A pull request that edits a listed workflow file can add a non-agent job there, and that job's failure becomes non-blocking. Review is the control.
- Scheduled workflows now wait for a click. An unattended run stalls until a reviewer approves or the run times out.
- Until this change merges, `origin/main` has no list, the reader warns, and nothing is exempt.

### Neutral

- `claude.yml` keeps its own authorization model and gains an unprotected environment.

## Impact on Dependent Components

| Component | Change |
|-----------|--------|
| Ten workflows and `claude.yml` | `environment: agent-approval` on each model job, `agent-claude` on the Claude job |
| `.claude/skills/pr-review/pr-review-config.yaml` and mirrors | New `advisory_agent_workflows` list |
| `.claude/skills/github/scripts/pr/test_pr_merge_ready.py` and mirrors | Reads the list from the trusted ref, exempts by workflow path, both GraphQL queries select `resourcePath` |
| ADR-057 | `/spec` leg is non-blocking and approval-gated |
| `gate-ladder.md`, `docs/COST-GOVERNANCE.md`, `ci-scripts.md`, `spec_extract_refs.py` | Stop describing `Validate Spec Coverage` as blocking or required |

## Reversibility Assessment

| Criterion | Assessment |
|-----------|------------|
| Rollback | Revert the pull request. The jobs return to `bot-secrets` and the list disappears. No data migrates. |
| External dependency | GitHub environments and required reviewers. A change to that feature changes this gate. |
| Partial rollback | Remove one entry to make that workflow's check blocking again, or remove its `environment` line. |

## Related Decisions

- ADR-101: Enforcement Planes. Required contexts match by name. Line 261 rejects environment reviewers as a fix, and this ADR overrides that for spend control.
- ADR-059: the completion gate dispatcher that byte-compares the config and dispatched files against the trusted ref.
- ADR-113: governed exceptions with rationale, owner, and expiry. The deferred registry merge would align this list with it.
- ADR-057: Prompt Behavioral Evaluation. Amended to mark the `/spec` leg non-blocking and approval-gated.

## References

- Issue #4902: non-required failure dispositions.
- Pull request #6131: the change that implements this ADR.
- Pull request #6130: the live pull request used to confirm the `resourcePath` field.
