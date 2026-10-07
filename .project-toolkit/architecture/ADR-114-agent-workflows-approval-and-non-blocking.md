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

Ten workflows call a model or an agent, and `claude.yml` answers `@claude` mentions with one, and they start on pull request events, schedules, issue labels, or dispatch with no person in the loop. The readiness check also lets their results hold a merge: `test_pr_merge_ready.py` blocks a failed non-required check that has no disposition (issue #4902), and with `--include-non-required` it blocks a waiting or pending one too. The owner set the policy that no agent workflow starts without approval and none blocks a merge (decisions D4, D6, D8 to D12), and ADR-057 says the `/spec` eval is a blocking CI leg, which conflicts with it.

## Decision

1. **Approval before running, one environment per provider.** Every job that calls a model declares the environment for the provider whose secret it reads: `agent-claude`, `agent-copilot`, `agent-codex`, or `agent-droid`. Each environment has required reviewers, so a run waits for a reviewer before the job starts, and each holds only its own provider's secrets. A job takes one environment, so these jobs swap `environment: bot-secrets` for their provider environment. The first version of this ADR used a single `agent-approval` environment. The owner replaced it with per-provider environments so each key lives in one place and a job can read only the key it needs. No workflow uses `agent-approval` now. The `bot-secrets` environment holds 0 secrets and 0 variables (Environments API, 2026-10-02), so the swap moves no secret or variable. A comment in `ai-spec-validation.yml` once said the job "holds an environment secret". That comment predated the API check and was stale, and this change rewords it.

2. **Eleven workflows are in scope.** Gated jobs:

   | Workflow | Gated job | Environment | Model call |
   |----------|-----------|-------------|------------|
   | `ai-spec-validation.yml` | `validate-spec` | `agent-claude` | `.github/actions/ai-review` with `ANTHROPIC_API_KEY` |
   | `slash-command-quality.yml` | `validate-slash-commands` | `agent-claude` | `ANTHROPIC_API_KEY`, `scripts/eval/eval-prompt-change.py` |
   | `post-pr-retrospective.yml` | `retrospective` | `agent-claude` | `anthropics/claude-code-action` with `CLAUDE_CODE_OAUTH_TOKEN` |
   | `software-engineering-library-activation.yml` | `activation-gate` | `agent-claude` | `ANTHROPIC_API_KEY` |
   | `skill-overlap-eval.yml` | `run-eval` | `agent-claude` | `ANTHROPIC_API_KEY` |
   | `ai-metrics-analysis.yml` | `analyze-metrics` | `agent-copilot` | `.github/actions/ai-review` with `COPILOT_GITHUB_TOKEN` |
   | `pr-maintenance.yml` | `process-prs` | `agent-copilot` | `.github/actions/ai-review` with `COPILOT_GITHUB_TOKEN` |
   | `artifact-insight-scanner.yml` | `scan-artifacts` | `agent-copilot` | `.github/actions/ai-review` with `COPILOT_GITHUB_TOKEN` |
   | `copilot-context-synthesis.yml` | `synthesize-single`, `sweep-missed` | `agent-copilot` | assigns the issue to the Copilot agent after synthesizing context |
   | `claude.yml` | `claude-response` | `agent-claude` | `anthropics/claude-code-action` with `CLAUDE_CODE_OAUTH_TOKEN` |
   | `nightly-cli-smoke.yml` | `smoke` (matrix `cli` x `os`) | `agent-${{ matrix.cli }}` | each leg runs one CLI (`claude -p` or `copilot -p`) through `tests/e2e/test_cli_hook_e2e.py` and `tests/e2e/test_plugin_load_smoke.py`, with only that CLI's key |

   The smoke job was one leg per OS that ran both CLIs with both keys. A job takes one environment, so the matrix now splits by CLI and each leg gets one provider's key. No workflow calls Codex or Droid yet. Their environments exist so a future job has a scoped key from the start.

   Jobs in those workflows that call no model keep their existing environment.

3. **`claude.yml` is approval-gated too.** Its `claude-response` job runs in `agent-claude`, which has required reviewers, so each `@claude` reply waits for a click. The first version of this ADR excluded `claude.yml` because an approval click per reply defeats its interactive purpose. The owner reversed that on 2026-10-07: no agent run starts without approval. The workflow keeps its own authorization check (`check-authorization`, `tests/workflows/test_claude_authorization.py`), which still runs before the job asks for approval. The approval controls spend, not prompt injection: the approval screen shows the job, not the comment or pull request text that drives the agent. A reviewer reads the triggering event before approving. `claude.yml` triggers on `pull_request`, so its check appears on pull requests. A rejected or timed-out approval would leave a failed non-required check, which blocks under issue #4902. `claude.yml` is therefore added to `advisory_agent_workflows`. The list works per file, so a failure of its `check-authorization` job is also non-blocking. Review of the workflow diff is the control, as for the other listed files.

4. **Checks are advisory, identified by workflow file.** A non-required check is exempt from blocking only when its CheckRun belongs to a listed workflow file. The identity is read from `checkSuite.workflowRun.workflow.resourcePath`, which maps to `.github/workflows/<file>`. The GraphQL `Workflow` type has no `path` field (introspected 2026-10-02: `createdAt`, `databaseId`, `id`, `name`, `resourcePath`, `runs`, `state`, `updatedAt`, `url`). A check name is free text any workflow can reuse, so a name list lets an unrelated check borrow a listed name. The resource path must also match the pull request's own repository. Both GraphQL queries select the field, including the pagination query, and a test pins that.

5. **The list is `advisory_agent_workflows` in `.claude/skills/pr-review/pr-review-config.yaml`.** Each entry has `path`, `reason`, and `owner` (`rjmurillo`). It holds the five gated workflows that trigger on `pull_request`: `ai-spec-validation.yml`, `slash-command-quality.yml`, `post-pr-retrospective.yml`, `software-engineering-library-activation.yml`, and `claude.yml` (Decision 3). The other six are gated but not listed. Their triggers are schedule, issue label, or dispatch only. A scheduled run attaches to the default branch and posts no check on a pull request. A `workflow_dispatch` run on a pull request branch is different: GitHub attaches check runs to the commit, so such a run is expected to appear in that pull request's rollup (expected from the commit-scoped check model, not observed here). If that run fails, its non-required check blocks until a disposition covers it. The owner chose the pruned list and accepts this residual. Trigger to revisit: the first dispatch of an unlisted agent workflow on a pull request branch.

6. **The list is read from the trusted ref.** `test_pr_merge_ready.py` runs `git show origin/main:<config>` and never reads the work tree, so a pull request that edits its copy cannot exempt its own failing check (CWE-829). When the ref or the list cannot be read (absent ref, shallow clone without the ref, parse error, no git), the reader returns an empty list and prints a stderr warning naming the reason. Empty means every check keeps its normal verdict. The reader skips the load when `ignore_ci` is set. The completion gate's criterion command names `test_pr_merge_ready.py`, so the gate byte-compares that script against the trusted ref before it runs (dispatched-file trust, ADR-059). A direct run of the script from a pull request tree, outside the gate, is not covered. Trigger to revisit: the first exemption-related incident.

7. **Precedence.** A check the branch ruleset requires stays blocking even when its workflow is listed. The reader uses GitHub's `isRequired` field. A StatusContext row has no workflow run, so it stays blocking. A name shared by a listed and an unlisted row is not exempt. `why_pr_blocked.py` reports required checks only and never reports a non-required one, so it already agrees with the exemption and needs no shared helper. A test pins both halves.

8. **Failed is non-blocking by design.** For a listed workflow, a check that is waiting, queued, pending, in progress, skipped, cancelled, timed out, or failed never blocks `CanMerge`. An agent verdict is advisory, and a reviewer reads it.

9. **`merge_group` leaves `ai-spec-validation.yml`.** Approval cannot happen inside a merge-queue run, and `validate-spec` was the only job the trigger fed. The `if:` term stays as a guard. The ADR-101 line references to this file (`:102`, `:97-102`) were already stale before this change: the `if:` that holds `always()` sits at line 87 on `main`.

10. **The gate is not a trust boundary.** ADR-101:269 states that a stanza on a job in a head-defined workflow contains nothing: the pull request can delete the stanza and request the repository-level secret directly. It also rejects an environment with required reviewers as the fix, because it reintroduces a human decision on every pull request. This ADR overrides that rejection for spend control only, by owner decision. The provider environments are repository configuration, which is plane P2 in ADR-101. The `environment:` line in a workflow is P0 content a writer can edit. The gate binds only when the model secrets are scoped to the environment. Then a job that deletes the stanza receives no secret, and a job that keeps it waits for a reviewer. `copilot-context-synthesis.yml` reads no provider secret, only `GITHUB_TOKEN`, so its gate rests on the stanza alone: a branch edit that deletes the stanza runs it without approval.

11. **Owner actions and their state.** The gate binds only when each model secret is scoped to its environment. State on 2026-10-07, read from the Environments and Actions secrets APIs:
    1. Done. `agent-claude`, `agent-copilot`, `agent-codex`, and `agent-droid` exist, each with required reviewer `rjmurillo`. "Prevent self-review" is off: the owner is the only reviewer, and with it on, no run the owner starts could be approved. Trigger to revisit: a second reviewer is added.
    2. Done. Secrets: `agent-claude` holds `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN`, `agent-copilot` holds `COPILOT_GITHUB_TOKEN`, `agent-codex` holds `OPENAI_API_KEY`, and `agent-droid` holds `FACTORY_API_KEY`. The names follow each vendor's documented variable.
    3. Done. The repository-level `ANTHROPIC_API_KEY` is deleted.
    4. Open. Repository-level `SMOKE_ANTHROPIC_API_KEY` and `FACTORY_API_KEY` remain. No workflow on `main` reads them, but a job on a branch that names them runs without approval. `FACTORY_API_KEY` also shadows the `agent-droid` copy: a job that omits the environment line still gets the repository copy. The Dependabot secret store holds 0 secrets (2026-10-07).
    5. Open. `BOT_PAT` appears in no environment and not in the repository secret list. `validate-spec`, `analyze-metrics`, `scan-artifacts`, and `process-prs` read it, so they run with an empty value until it exists. This was already true before this change. Split it into a model-only token for `ai-review` and the tokens that act on pull requests, and scope the model token to its environment.
    6. Open. `agent-approval` still exists with a required reviewer and 0 secrets, and no workflow uses it. The owner decides whether to delete it. Until then it is configuration that nothing reads.
    7. Residual. The owner is the only reviewer and self-review is allowed, so any process holding the owner's token can approve its own pending deployment through the REST API (`pending_deployments`). An agent that runs with that token can therefore start and approve a gated job with no human act. A deny rule in agent settings only slows this, because other spellings of the call exist. Trigger to revisit: a second reviewer is added, or self-review is turned off.

12. **An unprotected environment fails silently.** GitHub's documentation says "Running a workflow that references an environment that does not exist will create an environment with the referenced name" (docs.github.com, "Managing environments for deployment", read 2026-10-07). The created environment has no required reviewers. PR #6131 observed this: `agent-approval` first appeared with no protection rules. Then runs are unapproved and their checks still never block, so nothing signals the gap. Residual spend actors even when the environments are protected: a writer who edits a workflow on a branch, and a writer who dispatches a workflow. A writer can also point a branch job at any unprotected environment, which matters only when that environment holds a secret. As of 2026-10-07 the environments are `agent-claude`, `agent-codex`, `agent-copilot`, and `agent-droid` (required reviewers, provider secrets), `agent-approval` (required reviewers, 0 secrets, unused), and `bot-secrets`, `copilot`, and `vendor-provenance` (no reviewers, 0 secrets).

## Deferred Items

| Item | Why deferred | Trigger to revisit |
|------|--------------|--------------------|
| In-repo probe that each provider environment has required reviewers | Reading protection rules needs an admin-scoped token. CI has none. | An admin-scoped CI token exists. |
| Registry expiry for the list, and merging it into `dispositions.json` | Five entries with one owner do not need a registry. | The list exceeds 12 entries, or a second consumer of the list appears. |
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

The owner set the policy. The readiness check cannot express "never blocks" without an exemption, and ADR-101:269 had rejected approval environments, so the override needs a record.

## Rationale

The exemption is keyed on the workflow file because a check name is free text and a workflow path is not. The list that names the path lives where the completion gate already verifies trust. A check from `pytest.yml` with the job name `Validate Spec Coverage` must still block, and a test pins that case.

Required precedence follows ADR-101: a required context is matched by name in the ruleset, so a listed workflow cannot lower a requirement. Failed is non-blocking because the policy treats every agent verdict as advisory.

## Consequences

### Positive

- With environment-scoped secrets, no job that reads a model key starts without a reviewer click. `copilot-context-synthesis.yml` is the exception named in Decision 10.
- A model outage, a refusal, or a skipped run never holds a merge.
- A pull request cannot exempt its own failing check by editing the list.

### Negative

- Until the open owner actions in Decision 11 are done, the remaining repository-level model secrets stay a bypass for a job that names them.
- Every `claude.yml` run waits for a reviewer click, so it is no longer interactive when the owner is away. Runs are more frequent than `@claude` replies: the mention check reads the pull request title and body on `synchronize`, so a pull request whose body mentions `@claude` asks for approval on every push. The last 200 runs (Actions API, 2026-10-07) were 64 `pull_request_review_comment`, 59 `pull_request_review`, 36 `issue_comment`, 24 `pull_request`, and 17 `issues` events. `claude.yml` has no concurrency group, so unapproved runs accumulate in the waiting state. Trigger to revisit: waiting runs crowd out review, or the owner misses an approval that mattered. The likely fix is a concurrency group per issue or pull request with `cancel-in-progress: true`.
- The nightly smoke runs twice as many legs, one per CLI and OS, so its runner minutes roughly double, including the macOS legs. A run waits on two environments, `agent-claude` and `agent-copilot`. One review can approve both, because the pending-deployments review takes a list of environment IDs (REST API, "Workflow runs", read 2026-10-07). The workflow cancels an in-progress run when a new one starts, so a dispatch or the next scheduled run cancels legs still waiting for approval.
- Prompt regressions are no longer caught automatically before merge. The `/spec` eval runs only after approval. Review of prompt-file diffs is human-only, with no named owner for dispatching the eval, until the first prompt regression found after merge (ADR-057 Amendment 2026-10-02).
- A pull request that edits a listed workflow file can add a non-agent job there, and that job's failure becomes non-blocking. Review is the control.
- Scheduled workflows now wait for a click. An unattended run stalls until a reviewer approves or the run times out.
- Until this change merges, `origin/main` has no list, the reader warns, and nothing is exempt.

### Neutral

- `claude.yml` keeps its own authorization model, and its environment now carries required reviewers.

## Impact on Dependent Components

| Component | Change |
|-----------|--------|
| Ten workflows and `claude.yml` | Each model job declares its provider environment (`agent-claude` or `agent-copilot`); the smoke matrix splits by CLI |
| `.claude/skills/pr-review/pr-review-config.yaml` and mirrors | New `advisory_agent_workflows` list, with `claude.yml` added in the follow-up |
| `.claude/skills/github/scripts/pr/test_pr_merge_ready.py` and mirrors | Reads the list from the trusted ref, exempts by workflow path, both GraphQL queries select `resourcePath` |
| ADR-057 | `/spec` leg is non-blocking and approval-gated |
| `gate-ladder.md`, `docs/COST-GOVERNANCE.md`, `ci-scripts.md`, `spec_extract_refs.py` | Stop describing `Validate Spec Coverage` as blocking or required |

## Reversibility Assessment

| Criterion | Assessment |
|-----------|------------|
| Rollback | Revert the pull requests. The jobs return to `bot-secrets` and the list disappears. `bot-secrets` holds no secrets and the repository-level `ANTHROPIC_API_KEY` is deleted, so the owner must re-create the repository-level secrets in the same step, or every model job runs with an empty key. |
| External dependency | GitHub environments and required reviewers. A change to that feature changes this gate. |
| Partial rollback | Remove one entry to make that workflow's check blocking again, or remove its `environment` line. |

## Related Decisions

- ADR-101: Enforcement Planes. Required contexts match by name. Line 269 rejects environment reviewers as a fix, and this ADR overrides that for spend control.
- ADR-059: the completion gate dispatcher that byte-compares the config and dispatched files against the trusted ref.
- ADR-113: governed exceptions with rationale, owner, and expiry. The deferred registry merge would align this list with it.
- ADR-057: Prompt Behavioral Evaluation. Amended to mark the `/spec` leg non-blocking and approval-gated.

## References

- Issue #4902: non-required failure dispositions.
- Pull request #6131: the change that implements this ADR with one `agent-approval` environment.
- The follow-up pull request that moves each job to its provider environment and splits the smoke matrix.
- Pull request #6130: the live pull request used to confirm the `resourcePath` field.
