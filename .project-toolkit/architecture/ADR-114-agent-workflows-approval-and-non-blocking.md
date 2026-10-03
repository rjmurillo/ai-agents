---
id: ADR-114
status: proposed
date: 2026-10-03
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-114: Agent Workflows Run Only After Approval and Never Block Merges

## Context

Nine workflows call a model or an agent. They start on their own triggers: pull request events, a schedule, a push to main, or a manual dispatch. Each run spends model budget, and each run holds credentials. Two problems follow.

First, nothing asks a person before the spend or the credential use. A pull request from a same-repo branch starts `ai-spec-validation.yml`, `slash-command-quality.yml`, `post-pr-retrospective.yml`, and `software-engineering-library-activation.yml` with no approval.

Second, the readiness check treats an agent check as a merge signal. `test_pr_merge_ready.py` counts a failed non-required check as blocking unless `.project-toolkit/pr-checks/dispositions.json` carries a disposition for it (issue #4902). With `--include-non-required`, a pending or waiting non-required check blocks too. An agent verdict is advisory. A model outage or a refusal should not hold a merge.

ADR-057 also states, in several places, that the `/spec` eval in `slash-command-quality.yml` is the one blocking CI leg for prompt changes. That claim conflicts with this policy and needs an amendment.

Owner decisions D4, D6, D8, D9, and D10 set the policy below.

## Decision

1. **Approval before running.** Every job that calls a model declares `environment: agent-approval`. The environment carries required reviewers. A run waits for a reviewer before the job starts. A job takes one environment, so these jobs swap `environment: bot-secrets` for `environment: agent-approval`. The `bot-secrets` environment holds 0 secrets and 0 variables (checked with the Environments API on 2026-10-02), so no secret or variable changes scope.

2. **Nine workflows are in scope.** Gated jobs:

   | Workflow | Gated job |
   |----------|-----------|
   | `ai-spec-validation.yml` | `validate-spec` (check: Validate Spec Coverage) |
   | `slash-command-quality.yml` | `validate-slash-commands` |
   | `post-pr-retrospective.yml` | `retrospective` (check: Run retrospective agent) |
   | `software-engineering-library-activation.yml` | `activation-gate` |
   | `ai-metrics-analysis.yml` | `analyze-metrics` |
   | `pr-maintenance.yml` | `process-prs` |
   | `artifact-insight-scanner.yml` | `scan-artifacts` |
   | `skill-overlap-eval.yml` | `run-eval` |
   | `nightly-cli-smoke.yml` | `smoke` (matrix: ubuntu-latest, macos-latest, windows-latest) |

   Jobs in those workflows that call no model keep their existing environment.

3. **`claude.yml` is excluded and unchanged.** It answers a human `@claude` mention or an assigned issue, and it already runs its own authorization check (`check-authorization`, `tests/workflows/test_claude_authorization.py`). An approval click per reply would defeat the interactive purpose. The owner chose the exclusion. This ADR records it and does not argue it further.

4. **Checks are advisory, identified by workflow file.** A non-required check is exempt from blocking only when its CheckRun belongs to a listed workflow file. The identity is the file, read from the CheckRun's `checkSuite.workflowRun.workflow.resourcePath`, which maps to `.github/workflows/<file>`. The GraphQL `Workflow` type has no `path` field (introspected on 2026-10-02: `createdAt`, `databaseId`, `id`, `name`, `resourcePath`, `runs`, `state`, `updatedAt`, `url`), so `resourcePath` is the source. A check name is free text that any workflow can reuse, so a name list lets an unrelated check borrow a listed name. The resource path must also match the pull request's own repository.

5. **The list is `advisory_agent_workflows` in `.claude/skills/pr-review/pr-review-config.yaml`.** Each entry carries `path`, `reason`, and `owner` (`rjmurillo`). The list holds the four workflows that trigger on `pull_request`: `ai-spec-validation.yml`, `slash-command-quality.yml`, `post-pr-retrospective.yml`, and `software-engineering-library-activation.yml`. The other five are environment-gated but not listed. They run on a schedule or a dispatch, so they post no check on a pull request and nothing needs exempting.

6. **The list is read from the trusted ref.** `test_pr_merge_ready.py` runs `git show origin/main:<config>`. It never reads the work tree. A pull request that edits the list changes only its own copy, so it cannot exempt its own failing check (CWE-829). The completion gate separately byte-compares the same config against the trusted ref (ADR-059). When the ref or the list cannot be read (absent ref, shallow clone without the ref, parse error, git missing), the reader returns an empty list and prints a warning to stderr naming the reason. Empty means every check keeps its normal verdict.

7. **Precedence.** A check the branch ruleset requires stays blocking even when its workflow is listed. The reader uses GitHub's `isRequired` field, so a ruleset change takes effect without a code change. A StatusContext row has no workflow run, so it always stays blocking. A name shared by a listed and an unlisted row is not exempt.

8. **Failed is non-blocking by design.** For a listed workflow, a check that is waiting for approval, queued, pending, in progress, skipped, cancelled, timed out, or failed never blocks `CanMerge`. Failed is included on purpose. An agent verdict is advisory, and a reviewer reads it.

9. **`merge_group` leaves `ai-spec-validation.yml`.** Approval cannot happen inside a merge-queue run. `validate-spec` was the only job the trigger fed, and it already skipped on `merge_group`. The `if:` term stays as a guard so the line references in ADR-101 remain true.

10. **Precondition before merge.** The owner creates the `agent-approval` environment in repository Settings > Environments with required reviewers. If the environment does not exist, GitHub creates it on first use with no protection, and the jobs run without approval. As of 2026-10-02 the environments are `bot-secrets`, `copilot`, and `vendor-provenance`.

## Deferred Items

| Item | Why deferred | Trigger to revisit |
|------|--------------|--------------------|
| In-repo probe that `agent-approval` has required reviewers | Reading protection rules needs an admin-scoped token. CI has none. | An admin-scoped CI token exists. |
| Registry expiry for the list, and merging it into `dispositions.json` | Four entries with one owner do not need a registry. | The list exceeds 12 entries, or a second consumer of the list appears. |
| Auditing which listed workflow files a pull request edited | Review reads the diff today. | A listed workflow is edited to carry a non-agent job. |

## Alternatives Considered

| Alternative | Pros | Cons | Verdict |
|-------------|------|------|---------|
| Bare check-name list | Simple to read and test | Any workflow can emit a check with a listed name, and the check escapes blocking | Rejected: spoofable |
| Add each check to `dispositions.json` | Reuses an existing registry with expiry | A disposition names a failed check, not a state: waiting and pending checks still block with `--include-non-required`. Entries expire, so agent checks would need renewal | Rejected for now |
| Keep checks blocking, gate only the start | No change to readiness logic | A run that waits for approval blocks every pull request until someone clicks | Rejected |
| Disable the workflows | No spend | Loses the advisory signal and the scheduled analyses | Rejected |
| Environment approval plus a workflow-path exemption read from the trusted ref | Approval before spend, no block, no spoof by name or by a branch edit | Depends on a GitHub environment that someone must create and keep protected | Chosen |

## Prior Art Investigation

### What Currently Exists

- **Environment use:** 16 jobs named `environment: bot-secrets` before this change. `bot-secrets` has no protection rules and no deployment branch policy (ADR-101 records the same for all environments).
- **Non-required failure handling:** `_check_nonrequired_dispositions` in `test_pr_merge_ready.py` blocks a failed non-required check that has no accepted disposition (issue #4902).
- **Trust of config:** `run_completion_gate.py` byte-compares `pr-review-config.yaml` against `origin/main` before it runs any criterion (ADR-059).

### Why Change Now

The owner set the policy that no agent workflow starts without approval and none blocks a merge. The readiness check cannot express the second half without an exemption.

## Rationale

The exemption is keyed on the workflow file because a check name is free text and a workflow path is not. The list that names the path lives where the completion gate already verifies trust. A name-keyed list fails the spoof test: a check from `pytest.yml` with the job name `Validate Spec Coverage` must still block, and a test pins that case.

Required-check precedence follows ADR-101. A required context is matched by name in the ruleset, so a listed workflow cannot lower a requirement.

Failed is non-blocking because the policy treats every agent verdict as advisory. Treating failed as blocking would keep a model outage as a merge gate.

## Consequences

### Positive

- No model spend or credential use starts without a reviewer click.
- A model outage, a refusal, or a skipped run never holds a merge.
- A pull request cannot exempt its own failing check by editing the list.
- Four of nine workflows are exempt by path with an owner and a reason on each entry.

### Negative

- Prompt regressions are no longer caught automatically before merge. The `/spec` eval runs only after approval. The PR reviewer owns dispatching or approving the eval for any prompt-file diff and reading the result (ADR-057 Amendment 2026-10-02).
- The policy depends on a GitHub environment that an owner must create and keep protected. An unprotected `agent-approval` makes the gate decorative. No CI probe checks it yet.
- A pull request that edits a listed workflow file can add a non-agent job there, and that job's failure becomes non-blocking. Review of the workflow diff is the control.
- Scheduled workflows now wait for a click. An unattended run stalls until a reviewer approves or the run times out.
- Until this change merges, `origin/main` has no list, the reader warns, and nothing is exempt.

### Neutral

- `claude.yml` keeps its own authorization model.

## Impact on Dependent Components

| Component | Change |
|-----------|--------|
| Nine workflows | `environment: agent-approval` on each model job |
| `.claude/skills/pr-review/pr-review-config.yaml` and its plugin mirrors | New `advisory_agent_workflows` list |
| `.claude/skills/github/scripts/pr/test_pr_merge_ready.py` and mirrors | Reads the list from the trusted ref, exempts by workflow path, extends both GraphQL queries with `checkSuite.workflowRun.workflow.resourcePath` |
| ADR-057 | `/spec` leg is non-blocking and approval-gated |
| `gate-ladder.md`, `docs/COST-GOVERNANCE.md` | Agent workflows no longer listed as blocking |

## Reversibility Assessment

| Criterion | Assessment |
|-----------|------------|
| Rollback | Revert the pull request. The workflows return to `bot-secrets` and the list disappears. No data migrates. |
| External dependency | GitHub environments and required reviewers. A change to that feature changes this gate. |
| Partial rollback | Remove one entry from the list to make that workflow's check blocking again, or remove its `environment: agent-approval` line. |

## Related Decisions

- ADR-101: Enforcement Planes. Required contexts match by name, and environments carry no branch policy.
- ADR-059: the completion gate dispatcher that byte-compares the config against the trusted ref.
- ADR-113: governed exceptions with rationale, owner, and expiry. The deferred registry merge would align this list with it.
- ADR-057: Prompt Behavioral Evaluation. Amended to mark the `/spec` leg non-blocking and approval-gated.

## References

- Issue #4902: non-required failure dispositions.
- Pull request #6131: the change that implements this ADR.
- Pull request #6130: the live pull request used to confirm the `resourcePath` field.
