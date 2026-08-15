#!/usr/bin/env python3
"""Detect and alert on required-context drift from the live GitHub ruleset.

EXIT CODES (ADR-035):
  0 - live and pinned contexts match
  1 - drift detected and alert published when requested
  2 - local configuration error
  3 - GitHub API or issue operation failed
  4 - GitHub authentication failed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.ci.ruleset_required_contexts import (  # noqa: E402
    BRANCH,
    REFRESH_COMMAND,
    REPOSITORY,
    REQUIRED_CONTEXTS,
    RULESET_ID,
)
from scripts.github_core.checks_rollup import fetch_ruleset_required_contexts  # noqa: E402

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

ALERT_TITLE = "Ruleset Required Context Drift Detected"
ALERT_MARKER = "RULESET-CONTEXT-DRIFT"
ALERT_LABELS = "bug,area-workflows,drift-detected,automated"
ISSUE_SCRIPT_DIR = Path(".claude/skills/github/scripts/issue")


def query_live_contexts() -> set[str]:
    """Read the required contexts that currently apply to main."""
    owner, repo = REPOSITORY.split("/", maxsplit=1)
    contexts = fetch_ruleset_required_contexts(owner, repo, BRANCH)
    if contexts is None:
        raise RuntimeError("GitHub did not return the required-context rules")
    return set(contexts)


def compare_contexts(
    live: set[str],
    pinned: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return contexts added to and removed from the live ruleset."""
    return tuple(sorted(live - pinned)), tuple(sorted(pinned - live))


def _format_contexts(contexts: Sequence[str]) -> str:
    if not contexts:
        return "- None"
    return "\n".join(f"- `{context}`" for context in contexts)


def render_alert(
    live: set[str],
    pinned: set[str],
    added: Sequence[str],
    removed: Sequence[str],
) -> str:
    """Build the actionable issue body for a detected divergence."""
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = (
        f"{server_url}/{REPOSITORY}/actions/runs/{run_id}"
        if run_id
        else "Local check"
    )
    return f"""<!-- {ALERT_MARKER} -->
## Ruleset Required Context Drift

**Ruleset**: `{RULESET_ID}`
**Workflow run**: {run_url}

### Added to live ruleset

{_format_contexts(added)}

### Removed from live ruleset

{_format_contexts(removed)}

### Live contexts ({len(live)})

{_format_contexts(sorted(live))}

### Pinned contexts ({len(pinned)})

{_format_contexts(sorted(pinned))}

### Refresh command

```bash
{REFRESH_COMMAND}
```

Update `REQUIRED_CONTEXTS` in
`scripts/ci/ruleset_required_contexts.py`, then run:

```bash
uv run pytest tests/ci/test_merge_group_readiness.py \
  tests/ci/test_ruleset_context_drift.py
```
"""


def _run_issue_skill(
    script_name: str,
    arguments: Sequence[str],
) -> tuple[int, dict[str, Any]]:
    command = [
        sys.executable,
        str(ISSUE_SCRIPT_DIR / script_name),
        *arguments,
        "--output-format",
        "json",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"::error::{script_name} failed to start: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, {}

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        print(f"::error::{script_name} failed: {detail}", file=sys.stderr)
        if result.returncode in {EXIT_CONFIG, EXIT_EXTERNAL, 4}:
            return result.returncode, {}
        return EXIT_EXTERNAL, {}

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"::error::{script_name} returned invalid JSON: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, {}

    data = envelope.get("Data")
    if envelope.get("Success") is not True or not isinstance(data, dict):
        print(f"::error::{script_name} returned an error envelope", file=sys.stderr)
        return EXIT_EXTERNAL, {}
    return EXIT_OK, data


def _find_existing_alert() -> tuple[int, int | None]:
    owner, repo = REPOSITORY.split("/", maxsplit=1)
    rc, data = _run_issue_skill(
        "list_issues.py",
        [
            "--owner",
            owner,
            "--repo",
            repo,
            "--search",
            f'is:open in:title "{ALERT_TITLE}"',
            "--limit",
            "1",
        ],
    )
    if rc != EXIT_OK:
        return rc, None

    issues = data.get("issues")
    if not isinstance(issues, list) or not issues:
        return EXIT_OK, None
    number = issues[0].get("number") if isinstance(issues[0], dict) else None
    if not isinstance(number, int):
        print("::error::list_issues.py returned an invalid issue number", file=sys.stderr)
        return EXIT_EXTERNAL, None
    return EXIT_OK, number


def publish_alert(body: str) -> int:
    """Create one alert issue, or update its marked comment."""
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp:
        print("::error::RUNNER_TEMP is required with --alert", file=sys.stderr)
        return EXIT_CONFIG

    body_path = Path(runner_temp) / "ruleset-context-drift.md"
    try:
        body_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        print(f"::error::failed to write alert body: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    rc, issue_number = _find_existing_alert()
    if rc != EXIT_OK:
        return rc

    owner, repo = REPOSITORY.split("/", maxsplit=1)
    if issue_number is None:
        rc, _ = _run_issue_skill(
            "new_issue.py",
            [
                "--owner",
                owner,
                "--repo",
                repo,
                "--title",
                ALERT_TITLE,
                "--body-file",
                str(body_path),
                "--labels",
                ALERT_LABELS,
            ],
        )
        return rc

    rc, _ = _run_issue_skill(
        "post_issue_comment.py",
        [
            "--owner",
            owner,
            "--repo",
            repo,
            "--issue",
            str(issue_number),
            "--body-file",
            str(body_path),
            "--marker",
            ALERT_MARKER,
            "--update-if-exists",
        ],
    )
    return rc


def run(*, alert: bool) -> int:
    """Compare live and pinned contexts, then alert when requested."""
    try:
        live = query_live_contexts()
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    pinned = set(REQUIRED_CONTEXTS)
    added, removed = compare_contexts(live, pinned)
    print(
        f"Compared {len(live)} live contexts with "
        f"{len(pinned)} pinned contexts."
    )
    if not added and not removed:
        print("No required-context drift detected.")
        return EXIT_OK

    body = render_alert(live, pinned, added, removed)
    print(body)
    if not alert:
        return EXIT_DRIFT

    publish_rc = publish_alert(body)
    return EXIT_DRIFT if publish_rc == EXIT_OK else publish_rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect drift in the required status check contexts.",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Create or update the alert issue when drift is found.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(alert=args.alert)


if __name__ == "__main__":
    raise SystemExit(main())
