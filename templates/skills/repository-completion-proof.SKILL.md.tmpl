---
name: repository-completion-proof
version: 1.0.0
description: >-
  Prove ai-agents PR completion after review, recovery, or trust verification.
  Do NOT use for consumer behavior (use repository-consumer-proof).
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
      - prove an ai-agents PR is complete
      - verify before dispatching review commands
      - review is finished but completion is uncertain
      - completion verified true unresolved threads
      - PR already merged completion gate
      - verify only security threads
---

# Repository completion proof

Requires the `rjmurillo/ai-agents` checkout and its contributor-only sibling skills.

Inputs: PR number, intended acceptance criteria, and authorized task scope.
Apply the [common execution contract](../repository-pr-recovery/references/library.md#common-execution-contract).
Reuse the review config, `pr-comment-responder`, and the existing completion dispatcher.
This shortcut joins execution trust, criterion results, and platform acceptance.

## Triggers

- `prove an ai-agents PR is complete`
- `verify before dispatching review commands`
- `review is finished but completion is uncertain`

## Process

### Phase 1: Prove execution trust before dispatching review commands

Read config resolution in [pr-review](../../../.claude/skills/pr-review/SKILL.md).
Use that documentation without invoking its standalone orchestration workflow.
Use its command map for that host rather than inventing a launcher.
From the repository root, the POSIX checkout form is:

```bash
GITHUB_SCRIPTS="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
uv run python "$GITHUB_SCRIPTS/pr/run_completion_gate.py" --pull-request "$PR_NUMBER" --verify-config-only --json
```

Set `PR_NUMBER` from the current task.
Keep the default trusted remote-tracking ref unless the selected base requires another.
Any alternate anchor must resolve under `refs/remotes/`.
Do not substitute `HEAD` or a movable local branch to silence divergence.
Check anchor freshness against the selected remote revision through supported reads.
Fetching changes local Git state and requires the task's authority.

| Observation | Branch |
|---|---|
| Successful verification and `verified: true` | Begin verified finding handling. No completion claim follows yet. |
| Untrusted config or command file | Preserve the surfaced difference for human inspection. |
| Verification impossible | Restore verifiable Git evidence through an authorized owner; do not dispatch. |
| Installed config accepted by origin | Retain origin and command-trust evidence; run criteria before claiming success. |

Path containment does not establish execution trust.
A plugin root containing the consumer checkout is not disjoint.
The [dispatcher trust contract](../../../.claude/skills/github/scripts/pr/run_completion_gate.py)
checks the origin, remote anchor, and tracked command files separately.
Use `--approve-untrusted-config` only after explicit human inspection and approval.
Never use it for an unverifiable Git state.

### Phase 2: Execute completion criteria after verified review work

First read the current merged state through the verified `test_pr_merged.py` producer.
Use the selected config's launcher and inspect its JSON `merged` field.
If `merged` is true, inspect the merged artifact and requested downstream result.
Skip finding mutations and open-PR completion criteria on that branch.
An unavailable merged-state read leaves this decision unresolved.

Pass trust evidence and the selected config to `pr-comment-responder`.
For actual findings, let `reviewer-findings` verify claims before responder changes.
Reconcile outcomes per comment ID through `pr-comment-responder`.
An acknowledged thread or local reviewer verdict is an intermediate result.

Then execute the same dispatcher without verify-only:

```bash
uv run python "$GITHUB_SCRIPTS/pr/run_completion_gate.py" --pull-request "$PR_NUMBER" --json
```

This command dispatches configured verifiers; inspect their effects before execution.
Do not run it merely to test this library under a read-only task.
Use an existing authorized evidence destination if persistence is required.

Require successful execution, `all_passed: true`, and every configured criterion's result.
Inspect fail-open criteria and dispatch errors before claiming measured completion.
Check pagination completeness, suppressed-finding dispositions, and reachable resolution SHAs.
The [executable criteria](../../../.claude/skills/pr-review/pr-review-config.yaml)
currently require zero unresolved threads, including security threads.
Its nearby exemption comment does not override that predicate or platform policy.
Preserve unresolved security work for the responsible owner; do not force-resolve it.

For failures, route only the failing criterion back to its producer.
Use [repository-pr-recovery](../repository-pr-recovery/SKILL.md) when CI or policy attribution is uncertain.
Use existing dispositions procedures for deliberately unaddressed findings.
Do not manufacture approval markers or weaken predicates to make the gate green.
Run focused verification after edits, then the required full gate at the final head.

### Phase 3: Distinguish readiness, acceptance, and downstream completion

Join the criterion result with the effective-policy proof from `repository-pr-recovery`.
Verify required checks on the revision and event that GitHub evaluates.
Re-read readiness after a new commit, base update, or policy change.
If the PR already merged, inspect the merged artifact instead of failing its old readiness goal.
The open-PR completion config deliberately requires `merged == false`.

For authorized shipping, hand off to [ship](../../../.claude/skills/ship/SKILL.md).
Observe the merged state separately when the user requested a merged change.
For releases or consumer behavior, hand off to [repository-consumer-proof](../repository-consumer-proof/SKILL.md).
Keep operator-owned publication or adoption work visible until independently verified.

Report three separate results: execution trusted, criteria passed, requested outcome observed.
Name any inaccessible policy read and its responsible operator.
A successful verify-only invocation proves only the first result.

## Verification

- [ ] Trust evidence identifies the config, command files, and remote anchor.
- [ ] Executed criteria and platform evidence prove the requested outcome separately.

## Anti-Patterns

Do not substitute a successful intermediate invocation for the requested outcome.

## Evolution

Refresh the referenced producer when its contract or selected host changes.
Keep new acceptance requirements in their existing authoritative configuration.
