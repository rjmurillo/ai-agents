# SPEC-6182: Deterministic Validate Spec Coverage

Issue: #6182. Tier 3 (several CI scripts and two workflows). Domain: Complicated.

## Step 0 First Principles

### Q1 Demand Reality

The owner (rjmurillo) filed #6182. The readiness check (`test_pr_merge_ready.py`) needed a waiver for this check. Five open PRs (5979, 6104, 6107, 6131, 6150) were red on it at once.

### Q2 Status Quo

A PR author waits for a reviewer to approve the `agent-claude` environment. Two Claude calls then run. When the key is out of credit, the check goes red. The author asks the owner to add the PR to the `Validate Spec Coverage` waiver in `.project-toolkit/pr-checks/dispositions.json`.

### Q3 Desperate Specificity

PR authors whose check is red from a credit, token, or quota failure. They cannot clear it from their branch.

### Q4 Narrowest Wedge

Make the existing deterministic acceptance-criteria signal the only verdict of `Validate Spec Coverage`. Move the model review to its own approval-gated workflow that only comments. About four hours of AI-assisted work.

### Q5 Observation

Run 37220110465 failed with `credit balance is too low`. Run 37484227898 aborted at Load Spec Content. Issues #5738 and #6069 record a green pass that never ran.

### Q6 Future-fit

At 10x PR volume, a model call per PR costs 10x tokens and 10x approvals. A deterministic check costs nothing per PR. The approval-gated review scales with the reviewer's choice to approve, which is the cost control the owner asked for.

## Problem statement

`Validate Spec Coverage` gives its verdict from two model calls. Credential, credit, and quota failures turn it red or green regardless of the PR.

## User stories

- As a PR author, I see the same spec coverage verdict every time I rerun on the same PR body.
- As the owner, I approve each model review run, so I control token spend.
- As a PR author, a missing or expired model secret never changes my status check.

## Ontology

- **SpecCoverageCheck**: the `Validate Spec Coverage` job in `ai-spec-validation.yml`. Deterministic.
- **SpecReference**: an issue or spec file the PR title or body links (`spec_extract_refs.py`).
- **AcceptanceSection**: the PR body heading matching `acceptance( criteria)?` and its checkbox items (`acceptance_criteria.py`).
- **SpecReview**: the model review job in `ai-spec-review.yml`. Advisory, comment only, gated by the `agent-claude` environment.
- Decision rule: SpecCoverageCheck reads only the event payload and git. SpecReview never sets a failing conclusion from a verdict.

## Data model

Verdict inputs: `has_specs` (bool), PR body text. Verdict output: `PASS` or `FAIL` with a reason string. A run the scope step skips never reaches the verdict script. Invariant: same inputs give the same output.

| has_specs | AcceptanceSection | Verdict |
|-----------|-------------------|---------|
| false | any | PASS (no linked spec) |
| true | absent or no checkboxes | FAIL (owner decision D2) |
| true | any box unchecked | FAIL |
| true | all boxes checked | PASS |

## Integrations

- GitHub event payload (title, body, base and head SHA). No network call on `pull_request`.
- `workflow_dispatch` reads the PR body with `GH_TOKEN: github.token`. A fetch failure is a config error (exit 2), named in the log.
- SpecReview uses `ANTHROPIC_API_KEY` from `agent-claude` and posts through `github.token`.

## Failure modes

- PR body edited: `pull_request: edited` reruns the check. Same body gives same verdict.
- Model secret missing or out of credit: SpecReview logs a typed advisory line and posts no verdict. SpecCoverageCheck is unaffected.
- Parser false FAIL: an unusual checkbox format or a heading that does not match `acceptance( criteria)?`. Escape: edit the PR body to the template form. The edit re-runs the check.
- "Re-run jobs" replays the old event payload, so it sees the old body. A fresh `edited` event is the supported path.
- Reviewer never approves SpecReview: its run waits. It is listed in `advisory_agent_workflows`, so readiness does not block on it.

## Security

SpecCoverageCheck holds no secret and no environment. PR body text reaches scripts through `env:`, never interpolated into `run:` (CWE-78). SpecReview keeps the existing `agent-claude` gate (ADR-114).

## Observability

The check writes the verdict, reason, and each unchecked criterion to the step summary and an `::error::` line on FAIL.

## Acceptance criteria

1. The `Validate Spec Coverage` job shall declare no `environment:` and reference no `secrets.` value.
2. The `ai-spec-validation.yml` workflow shall contain no step that uses `./.github/actions/ai-review`.
3. When the PR links no spec, the check shall pass.
4. When the PR links a spec and the body has no acceptance checkbox section, the check shall fail and name the missing section.
5. When the PR links a spec and any acceptance box is unchecked, the check shall fail and list each unchecked item.
6. When the PR links a spec and every acceptance box is checked, the check shall pass.
7. When run twice on the same inputs, the check shall return the same verdict and exit code.
8. The model review shall run in `ai-spec-review.yml` behind `environment: agent-claude`, post a PR comment, and conclude success regardless of the model verdict or a model failure.
9. `ai-spec-review.yml` shall be listed in `advisory_agent_workflows`.
10. The `Validate Spec Coverage` entry shall be removed from `dispositions.json`.

## Out of scope

- Mapping issue acceptance criteria to changed files or named tests (issue candidate signals 2 and 3).
- Making the check blocking for readiness (owner decision D3: stays advisory).
- Changes to the shared `ai-review` action.

## Deferred

- Whether to remove `ai-spec-validation.yml` from `advisory_agent_workflows`. Owner: rjmurillo. Revisit after 30 days with no false FAIL reported.

## Open questions

None.

## CVA summary

Common: scope decision and spec reference extraction serve both workflows. Varies: the verdict source (deterministic parser vs model) and the failure policy (fail vs comment only).

## Buy-vs-build decision

Context, not core. The deterministic parser already exists in-tree (`acceptance_criteria.py`). Recommendation: reuse. No new capability.

## Complexity classification

Tier 3, Complicated. Methodology: test-first slices.
