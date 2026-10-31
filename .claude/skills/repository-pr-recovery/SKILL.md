---
name: repository-pr-recovery
version: 1.0.0
description: Attribute blocked ai-agents PRs, missing checks, and cancelled baselines. Do NOT use for completion proof (use repository-completion-proof).
license: MIT
metadata:
  distribution: repo-local
  capability:
    kind: orchestrator
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan selects this repository outcome composition from its intents
    user-facing: true
    intents:
      - recover a blocked ai-agents PR
      - attribute an ai-agents red check
      - required check never reports
      - required check matching main rows
      - check another integration prior head
      - check cancelled on main
      - missing required check
      - ai-agents PR PR_ONLY
---

# Repository PR recovery

Requires the `rjmurillo/ai-agents` checkout and its contributor-only sibling skills.

Use this shortcut to select the smallest legitimate recovery action.
Inputs: PR number, requested outcome, and authority to diagnose or change.
Apply the [common execution contract](references/library.md#common-execution-contract).
Reuse `github`, `reviewer-findings`, and `pr-comment-responder` only when their branch applies.

## Triggers

- `recover a blocked ai-agents PR`
- `attribute an ai-agents red check`
- `required check never reports`

## Process

### Phase 1: Identify the blocker before choosing a fix

Select GitHub transport through [github](../../../.claude/skills/github/SKILL.md).
Set `PR_NUMBER` from the supplied PR, never a remembered result.
For an available script transport, bind its installed root once:

```bash
GITHUB_SCRIPTS="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
python3 "$GITHUB_SCRIPTS/pr/why_pr_blocked.py" --owner rjmurillo --repo ai-agents --pull-request "$PR_NUMBER" --output-format json
```

Read the complete selected discussion and inline threads before acting on findings.
Use `get_pr_context.py`, `get_pr_review_threads.py`, and linked causal items.
Stop broad discovery once the blocker and responsible surface are identified.

Keep missing, queued, pending, failing, and unresolved-thread states separate.
The script allows recently absent checks a startup grace period.
A successful probe means no diagnosed blocker; it does not certify every effective policy.
See [the producer](../../../.claude/skills/github/scripts/pr/why_pr_blocked.py).

For a failed check, copy its exact display name into `CHECK_NAME`.
Set `BASE_BRANCH` from this PR's base branch.

```bash
python3 "$GITHUB_SCRIPTS/pr/triage_red_check.py" --owner rjmurillo --repo ai-agents --pull-request "$PR_NUMBER" --branch "$BASE_BRANCH" --check-name "$CHECK_NAME" --output-format json
```

Read `Data.Verdict`, evidence URL, run identity, and ambiguity fields together.
Exit codes alone cannot distinguish the three non-evidence verdicts.

| Observation | Next action |
|---|---|
| `GREEN_ON_MAIN` | Inspect the PR failure and reproduce the alleged regression. |
| `RED_ON_MAIN` | Compare failure signatures; report inherited failure with its evidence URL. |
| `PR_ONLY` | Confirm name, workflow triggers, and filters; read the PR run's logs. |
| `CANCELLED_ON_MAIN` | Identify the workflow and attempt; request an authorized rerun if needed. |
| `UNKNOWN`, incomplete pages, or ambiguous definitions | Resolve the missing evidence before attributing the failure. |

`PR_ONLY` means no matching row within the examined history.
It does not prove a workflow never runs on main.
Widen history only when schedule or path filters justify it, with `--history-depth` (max 50 commits).
Cancelled evidence may contain same-name workflows; validate identity before rerunning.
Different failure signatures can coexist even when both branches are red.
Read logs through `get_pr_check_logs.py`, not raw `gh`.
These branches reflect an accepted PR
and the [current verdict implementation](../../../.claude/skills/github/scripts/pr/triage_red_check.py).

### Phase 2: Join evidence to the actual acceptance policy

Use supported GitHub GET operations for these independent policy surfaces:

- `repos/rjmurillo/ai-agents/rulesets?includes_parents=true`, including pagination and each applicable detail.
- `repos/rjmurillo/ai-agents/rules/branches/<base>`, when the transport supports effective-rule reads.
- `repos/rjmurillo/ai-agents/branches/<base>/protection` for legacy protection.

Known ruleset `11104075` targets the default branch.
Inspect its detail directly; refresh the collection when scope or applicability changes.
The [ruleset](https://github.com/rjmurillo/ai-agents/rules/11104075) requires resolved threads and squash merges.
GitHub Actions integration ID `15368` is a verified producer coordinate.
Read current check contexts from policy instead of maintaining another list here.
Denied legacy-protection access remains unknown; an empty legacy result does not exclude rulesets.

Before accepting either green or red attribution, join the check's producer identity to the required integration:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/repository-pr-recovery/scripts/required_check_producer_join.py" --repo . --pr "$PR_NUMBER"
```

It pages the effective rules and the evaluated SHA's check-runs (`filter=all`) to the end, matching `name`, `app.id`, `head_sha`, and `check_suite.id`.
Each required context reads `produced-by-the-required-app`, `produced-by-another-app`, or `missing`.
Exit 0 means all produced, 1 means a finding, 2 bad arguments, 3 a failed or incomplete read (the error names the page).
It does not read legacy commit statuses, merge queues, or the workflow run behind a check-run.
The triage script matches names without integration identity; its verdict is provisional until this join agrees.
For Actions, read `repos/rjmurillo/ai-agents/actions/runs/<run-id>` and join `event`, `head_sha`, and `run_attempt` with the task's run metadata.
For legacy commit statuses, inspect `<sha>/statuses` through the commits endpoint.
If provider attribution cannot be verified, retain an unknown acceptance result.
If a merge queue applies, inspect the merge-group evaluation separately.
A same-name green check from another app, event, or revision is insufficient evidence.
`why_pr_blocked.py` supplies a cause list, not this entire policy join.

For missing checks, inspect workflow triggers and current job names before rerunning.
For a check rename, require evidence that both old and new names are emitted.
Route policy edits to the authorized owner after the new check actually runs.
Retain the old name until its requirement is removed through approved change control.
See [the overlap rule](../../../templates/rules/ci-scripts.md), MUST 22.
For review findings, invoke [reviewer-findings](../../../.claude/skills/reviewer-findings/SKILL.md)
before [pr-comment-responder](../../../.claude/skills/pr-comment-responder/SKILL.md).
Verify the reported defect before changing code or resolving a thread.
For inherited failures outside the requested branch, identify the owner without fixing unrelated scope.
For requested code changes, use existing build, test, review, and ship features.
Keep policy changes and bypasses outside this shortcut's authority.

### Phase 3: Prove recovery or hand off the exact remaining action

Return the blocker, attribution, revision, evidence URL, owner, and next authorized action.
If diagnosis was requested, stop after this evidence-backed answer.
If recovery was authorized, repeat the affected probe after the recovery action.
Pass the recovered PR and evidence to [repository-completion-proof](../repository-completion-proof/SKILL.md).
Claim recovery only when the actual blocker clears on the evaluated revision.
If policy access remains missing, name the exact read an authorized operator must perform.
Do not report the PR accepted or merged from a successful diagnosis alone.

## Scripts

List every linked instrument and confirm it exists:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/repository-pr-recovery/scripts/instruments.py" --repo . list
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/repository-pr-recovery/scripts/instruments.py" --repo . run <id> -- <args>
```

Ids: `why-pr-blocked`, `triage-red-check`, `check-logs`, `review-threads`, `required-context-conditions`, `producer-join`, `drift-self-check`.
`required-context-conditions` lints workflows that produce a pinned required context for hidden step conditions.
It does not prove a rename emits both names; that stays an evidence read of the workflow.

## Verification

- [ ] PR recovery evidence includes the blocker, revision, producer, and responsible owner.
- [ ] The actual blocker clears before recovery or acceptance is claimed.

## Anti-Patterns

Follow the [shared outcome boundary](references/library.md#common-execution-contract).

## Evolution

Follow the [shared maintenance policy](references/library.md#maintenance).

## Provenance and Maintenance

Checks live in `reverify.json`. Run the drift command after any edit:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name repository-pr-recovery --require
```
