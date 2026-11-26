# Workflow failure alert

## Symptom

- An issue titled "Workflow failed: `<workflow name>`" opens with the labels
  `bug`, `area-workflows`, and `automated`.
- The issue body links one failed run of an unattended workflow: a scheduled
  job, or a manual `npm Publish` dispatch.

[workflow-failure-alert.yml](../../.github/workflows/workflow-failure-alert.yml)
files it through
[workflow_failure_alert.py](../../scripts/ci/workflow_failure_alert.py). The
script reads only the run's event metadata. It never reads logs or artifacts.

## Confirm

1. Open the run URL in the issue. Read the failing step.
2. Check whether the same workflow failed on its previous schedule. The
   [Actions history](https://github.com/rjmurillo/ai-agents/actions) lists each
   workflow's runs. One red run after a green history is usually a flaky step or
   a GitHub outage. Repeated red runs are a defect.
3. A failed `npm Publish` dispatch: follow
   [npm publish or promotion gate failure](publish-failure.md). Do not publish
   again until you check the registry state it describes.

## Recover

1. Fix the cause on a branch and merge it through a pull request.
2. Re-run the workflow with `workflow_dispatch`, or wait for the next schedule.
3. Close the issue. Closing it re-arms the alert: the next failure opens a new
   issue. While an issue stays open, later failures of the same workflow update
   one marked comment on it. They do not add comments or open new issues.

## What is and is not watched

- Watched workflows are the `WATCHED` map in
  `scripts/ci/workflow_failure_alert.py`. `tests/ci/test_workflow_failure_alert.py`
  fails when a scheduled workflow is neither watched nor listed in
  `SELF_ALERTING`.
- Cancelled and skipped runs raise no alert. Only `failure`, `timed_out`, and
  `startup_failure` do.
- `npm Publish` alerts on a manual dispatch only. A red run from a `v*` tag push
  is expected until the tag ruleset exists (issue #5636).
- Pull request checks are not watched. They show on the pull request.
- `Check Ruleset Drift`, `Agent Drift Detection`, and
  `Ruleset Required Context Drift` file their own issues. See
  [Ruleset drift alert](ruleset-drift-alert.md) and
  [Agent drift alert](agent-drift-alert.md).
- `Python Tests` on `main` files its own issue. See
  [Red CI on main](red-ci-on-main.md).

## Failure modes

- The alert job itself fails (token, issue skill, or API error): the Actions tab
  shows a red "Workflow Failure Alert" run. The original failure is still red in
  its own run. No alert is a visible gap, not a silent pass.
- A bug in the script exits non-zero. Exit codes: 2 for a missing or unreadable
  event payload, 3 for a failed issue operation, 4 for authentication.
- A read-only eligibility job calls `workflow_failure_alert.py:parse_event`.
  Only eligible failures enter the publishing job's concurrency group.
  Ignored conclusions, triggers, branches, and metadata cannot cancel an alert.
  Eligible failures of one workflow share a group across allowed triggers.
  A later eligible publishing job supersedes an in-flight alert for that workflow.
  Classifier jobs run independently, so completion order can differ from event order.
  Check the surviving alert job if another shows as cancelled.
  An interrupted issue request can still produce duplicates. Close the duplicate.

## Privacy

The issue holds the workflow name, conclusion, trigger, short commit SHA, attempt
number, and run URL. All of it is already public in the repository's Actions tab.
Nothing leaves GitHub.

## Escalate

`@rjmurillo` owns the workflows and `scripts/ci/`. See the
[runbook index](README.md#owner).
