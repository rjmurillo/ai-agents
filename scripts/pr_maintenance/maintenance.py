"""PR Maintenance workflow operations extracted per ADR-006.

Provides functions for rate limit validation, log parsing, summary generation,
and alert issue body generation. For GitHub operations (creating issues,
posting comments), use the dedicated skill scripts.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class RateLimitResult:
    success: bool
    resources: dict[str, dict]
    summary_markdown: str
    core_remaining: int


@dataclass
class MaintenanceResults:
    processed: int
    acknowledged: int
    resolved: int
    blocked_prs: list[str] = field(default_factory=list)
    has_blocked: bool = False


@dataclass
class EnvironmentResult:
    valid: bool
    versions: dict[str, str]
    summary_markdown: str


DEFAULT_THRESHOLDS: dict[str, int] = {
    "core": 100,
    "search": 15,
    "code_search": 5,
    "graphql": 100,
}


def check_workflow_rate_limit(
    resource_thresholds: dict[str, int] | None = None,
) -> RateLimitResult:
    """Check GitHub API rate limits before workflow execution."""
    if resource_thresholds is None:
        resource_thresholds = dict(DEFAULT_THRESHOLDS)

    result = subprocess.run(
        ["gh", "api", "rate_limit"],
        capture_output=True,
        text=True,
        check=True,
    )
    rate_limit = json.loads(result.stdout)

    resources: dict[str, dict] = {}
    all_passed = True
    summary_lines = [
        "### API Rate Limit Status",
        "",
        "| Resource | Remaining | Threshold | Status |",
        "|----------|-----------|-----------|--------|",
    ]

    for resource, threshold in resource_thresholds.items():
        resource_data = rate_limit["resources"][resource]
        remaining = resource_data["remaining"]
        limit = resource_data["limit"]
        reset = resource_data["reset"]
        passed = remaining >= threshold

        if not passed:
            all_passed = False

        status = "OK" if passed else "TOO LOW"
        status_icon = "\u2705" if passed else "\u274c"

        resources[resource] = {
            "Remaining": remaining,
            "Limit": limit,
            "Reset": reset,
            "Threshold": threshold,
            "Passed": passed,
        }

        summary_lines.append(
            f"| {resource} | {remaining} | {threshold} | {status_icon} {status} |"
        )

    return RateLimitResult(
        success=all_passed,
        resources=resources,
        summary_markdown="\n".join(summary_lines),
        core_remaining=rate_limit["resources"]["core"]["remaining"],
    )


def get_maintenance_results(log_path: str | Path) -> MaintenanceResults:
    """Parse PR maintenance log file to extract metrics."""
    path = Path(log_path)

    if not path.exists():
        warnings.warn(f"Log file not found: {log_path}", stacklevel=2)
        return MaintenanceResults(
            processed=0,
            acknowledged=0,
            resolved=0,
            blocked_prs=[],
            has_blocked=False,
        )

    log = path.read_text(encoding="utf-8")

    processed = 0
    acknowledged = 0
    resolved = 0

    match = re.search(r"PRs Processed:\s*(\d+)", log)
    if match:
        processed = int(match.group(1))

    match = re.search(r"Comments Acknowledged:\s*(\d+)", log)
    if match:
        acknowledged = int(match.group(1))

    match = re.search(r"Conflicts Resolved:\s*(\d+)", log)
    if match:
        resolved = int(match.group(1))

    blocked_prs: list[str] = []
    blocked_match = re.search(
        r"(?s)Blocked PRs[^\n]*:\s*\n(.+?)(?:\n\s*\n|\Z)", log
    )
    if blocked_match:
        blocked_section = blocked_match.group(1)
        for line in blocked_section.split("\n"):
            stripped = line.strip()
            if stripped and re.search(r"PR\s*#\d+", stripped):
                blocked_prs.append(stripped)

    return MaintenanceResults(
        processed=processed,
        acknowledged=acknowledged,
        resolved=resolved,
        blocked_prs=blocked_prs,
        has_blocked=len(blocked_prs) > 0,
    )


def create_maintenance_summary(
    results: MaintenanceResults,
    core_remaining: int = 0,
    run_url: str = "",
) -> str:
    """Generate GitHub Actions step summary for PR maintenance run."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary = f"""## PR Maintenance Summary

**Run Time**: {timestamp}

| Metric | Value |
|--------|-------|
| PRs Processed | {results.processed} |
| Comments Acknowledged | {results.acknowledged} |
| Conflicts Resolved | {results.resolved} |
"""

    if results.has_blocked:
        blocked_list = "\n".join(results.blocked_prs)
        summary += f"""
### Blocked PRs (Require Human Action)

```
{blocked_list}
```
"""

    summary += f"""
### Rate Limit After Run

- Core API: {core_remaining} remaining
"""

    if run_url:
        summary += f"""
---
[View Logs]({run_url})"""

    return summary


def create_blocked_prs_alert(
    blocked_prs: list[str],
    run_url: str = "",
) -> str:
    """Generate issue body for blocked PRs alert."""
    blocked_list = "\n".join(blocked_prs)

    body = f"""## Blocked PRs

The automated PR maintenance workflow encountered PRs that require human action:

```
{blocked_list}
```

**Action Required**: Review the listed PRs and address blocking issues.
"""

    if run_url:
        body += f"""
**Workflow Run**: {run_url}
"""

    body += """
---
<sub>Powered by [PR Maintenance](https://github.com/rjmurillo/ai-agents) workflow</sub>"""

    return body


def create_workflow_failure_alert(
    run_url: str = "",
    trigger_event: str = "unknown",
) -> str:
    """Generate issue body for workflow failure alert."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""## Workflow Failure

The PR maintenance workflow failed during execution.

**Run**: {run_url}
**Trigger**: {trigger_event}
**Time**: {timestamp}

**Action Required**: Investigate workflow logs and resolve the issue.

---
<sub>Powered by [PR Maintenance](https://github.com/rjmurillo/ai-agents) workflow</sub>"""

    return body


def check_workflow_environment() -> EnvironmentResult:
    """Validate required tools are available for workflow execution."""
    versions: dict[str, str] = {}
    valid = True

    versions["Python"] = sys.version.split()[0]

    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        first_line = result.stdout.strip().splitlines()[0]
        versions["gh"] = re.sub(r"gh version\s*", "", first_line)
    except (subprocess.CalledProcessError, FileNotFoundError):
        versions["gh"] = "NOT FOUND"
        valid = False

    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        versions["git"] = re.sub(r"git version\s*", "", result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        versions["git"] = "NOT FOUND"
        valid = False

    summary_lines = [
        "### Environment Validation",
        "",
        "| Tool | Version |",
        "|------|---------|",
    ]

    for tool, version in versions.items():
        summary_lines.append(f"| {tool} | {version} |")

    return EnvironmentResult(
        valid=valid,
        versions=versions,
        summary_markdown="\n".join(summary_lines),
    )
