#!/usr/bin/env python3
"""Open or update one GitHub issue when a watched unattended workflow fails.

Scheduled and dispatch-only workflows run with nobody watching. A red run there
shows only in the Actions tab. This script turns the `workflow_run` event of a
watched workflow into one deduplicated issue, so the failure reaches the issue
notification channel that `docs/agent-readiness.md` names as the alert path.

The script reads the event payload file and nothing else from the run. It does
not read logs, artifacts, or secrets, and it sends nothing outside GitHub.

With `--classify`, the script only decides eligibility. It prints the reason
and writes `eligible=true` or `eligible=false` to GITHUB_OUTPUT.

EXIT CODES (ADR-035):
  0 - nothing to alert on, or the alert issue was created or updated
  2 - configuration error: no event file, unreadable payload, no RUNNER_TEMP,
      or with --classify a missing or unwritable GITHUB_OUTPUT
  3 - the issue operation failed
  4 - GitHub authentication failed
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.ci.ruleset_context_drift import publish_issue_alert  # noqa: E402
from scripts.ci.ruleset_required_contexts import BRANCH, REPOSITORY  # noqa: E402

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

ALERT_LABELS = "bug,area-workflows,automated"
RUNBOOK_PATH = "docs/runbooks/workflow-failure-alert.md"

_SCHEDULE = frozenset({"schedule", "workflow_dispatch"})

# Workflow name -> trigger events that may raise an alert. The names must match
# the `workflows:` list in `.github/workflows/workflow-failure-alert.yml`; a test
# pins both. `npm Publish` alerts on a manual dispatch only: a `v*` tag push
# fails by design until the tag ruleset exists (docs/runbooks/publish-failure.md).
WATCHED: Mapping[str, frozenset[str]] = {
    "Agent Metrics": _SCHEDULE,
    "Agent-Skill Discriminator Check": _SCHEDULE,
    "AI Metrics Analysis": _SCHEDULE,
    "Artifact Insight Scanner": _SCHEDULE,
    "Autoplan Route Eval": _SCHEDULE,
    "CodeQL Analysis": frozenset({"schedule"}),
    "Copilot Context Synthesis": _SCHEDULE,
    "Enforcement Closure": _SCHEDULE,
    "npm Publish": frozenset({"workflow_dispatch"}),
    "PR Maintenance": _SCHEDULE,
    "Skill Overlap Eval": _SCHEDULE,
    "Software Engineering Library Activation": _SCHEDULE,
    "Update Reviewer Signal Stats": _SCHEDULE,
    "Workflow Coalescing Metrics": _SCHEDULE,
}

# Scheduled workflows that already file their own alert issue. Listing them here
# records the decision so the coverage test can tell "chose not to watch" from
# "forgot to watch".
SELF_ALERTING = frozenset(
    {
        "Agent Drift Detection",
        "Check Ruleset Drift",
        "Ruleset Required Context Drift",
    }
)

FAILING_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})


@dataclass(frozen=True, slots=True)
class FailedRun:
    """The fields of a failed `workflow_run` event the alert needs."""

    name: str
    conclusion: str
    event: str
    url: str
    head_sha: str
    attempt: int


def parse_event(payload: object) -> FailedRun | str:
    """Return the failed run to alert on, or a string saying why not.

    Anything that is not a failure of a watched workflow on the default branch
    through an allowed trigger yields a reason string and no alert.
    """
    run = payload.get("workflow_run") if isinstance(payload, dict) else None
    if not isinstance(run, dict):
        return "payload has no workflow_run object"

    name = run.get("name")
    if not isinstance(name, str) or name not in WATCHED:
        return f"workflow {name!r} is not watched"

    conclusion = run.get("conclusion")
    if not isinstance(conclusion, str) or conclusion not in FAILING_CONCLUSIONS:
        return f"conclusion {conclusion!r} does not raise an alert"

    event = run.get("event")
    if not isinstance(event, str) or event not in WATCHED[name]:
        return f"trigger {event!r} does not raise an alert for {name}"

    if run.get("head_branch") != BRANCH:
        return f"run was on branch {run.get('head_branch')!r}, not {BRANCH}"

    url = run.get("html_url")
    if not isinstance(url, str) or not re.fullmatch(
        rf"https://github\.com/{re.escape(REPOSITORY)}/actions/runs/[1-9][0-9]*", url
    ):
        return "run has no valid repository run URL"

    attempt = run.get("run_attempt")
    sha = run.get("head_sha")
    return FailedRun(
        name=name,
        conclusion=str(conclusion),
        event=str(event),
        url=url,
        head_sha=sha[:12]
        if isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{12,40}", sha)
        else "unknown",
        attempt=attempt if type(attempt) is int and attempt > 0 else 1,
    )


def alert_title(name: str) -> str:
    return f"Workflow failed: {name}"


def alert_marker(name: str) -> str:
    return "WORKFLOW-FAILURE-" + re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()


def render_body(failed: FailedRun) -> str:
    """Build the issue body from event metadata only."""
    runbook = f"https://github.com/{REPOSITORY}/blob/{BRANCH}/{RUNBOOK_PATH}"
    workflows = f"https://github.com/{REPOSITORY}/actions"
    return f"""<!-- {alert_marker(failed.name)} -->
## Workflow failed: {failed.name}

| Field | Value |
|---|---|
| Conclusion | `{failed.conclusion}` |
| Trigger | `{failed.event}` |
| Commit | `{failed.head_sha}` |
| Attempt | {failed.attempt} |
| Run | {failed.url} |

**Runbook**: {runbook}
**All workflow runs**: {workflows}

Open the run, read the failing step, and fix the cause. Closing this issue
re-arms the alert: the next failure opens a new issue.
"""


def step0_evidence(failed: FailedRun) -> tuple[str, str]:
    """Return the Step 0 Q3 and Q5 answers `new_issue.py` requires."""
    blocked_by = (
        f"Maintainers of {REPOSITORY}: the unattended {failed.name} workflow "
        f"no longer completes its scheduled job."
    )
    signal = (
        f"Run {failed.url} ended with conclusion {failed.conclusion} "
        f"on trigger {failed.event} at commit {failed.head_sha}."
    )
    return blocked_by, signal


def run(payload: object) -> int:
    """Alert on one workflow_run payload."""
    parsed = parse_event(payload)
    if isinstance(parsed, str):
        print(f"No alert: {parsed}.")
        return EXIT_OK

    blocked_by, signal = step0_evidence(parsed)
    rc = publish_issue_alert(
        title=alert_title(parsed.name),
        marker=alert_marker(parsed.name),
        labels=ALERT_LABELS,
        body=render_body(parsed),
        body_filename="workflow-failure-alert.md",
        blocked_by=blocked_by,
        signal=signal,
    )
    if rc == EXIT_OK:
        print(f"Alert published for {parsed.name}: {parsed.url}")
    return rc


def load_payload(environ: Mapping[str, str]) -> tuple[int, Any]:
    """Read the event file named by GITHUB_EVENT_PATH."""
    event_path = environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("::error::GITHUB_EVENT_PATH is required", file=sys.stderr)
        return EXIT_CONFIG, None
    try:
        return EXIT_OK, json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::cannot read event payload: {exc}", file=sys.stderr)
        return EXIT_CONFIG, None


def classify(payload: object, environ: Mapping[str, str]) -> int:
    """Print why a completion is or is not eligible and write the `eligible` output.

    The eligibility job's `if:` reads `eligible=true|false` from GITHUB_OUTPUT.
    The printed reason lands in the step log, so a red run that filed no issue
    says why.
    """
    parsed = parse_event(payload)
    if isinstance(parsed, str):
        print(f"Skip: {parsed}.")
    else:
        print(f"Eligible: {parsed.name} ended {parsed.conclusion} on {parsed.event}: {parsed.url}")
    output_path = environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG
    line = f"eligible={str(not isinstance(parsed, str)).lower()}\n"
    try:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        print(f"::error::cannot write GITHUB_OUTPUT: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = argv or []
    if args not in ([], ["--classify"]):
        print("usage: workflow_failure_alert.py [--classify]", file=sys.stderr)
        return EXIT_CONFIG
    rc, payload = load_payload(os.environ)
    if rc != EXIT_OK:
        return rc
    if args:
        return classify(payload, os.environ)
    return run(payload)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
