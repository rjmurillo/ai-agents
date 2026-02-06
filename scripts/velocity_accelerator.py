"""Velocity Accelerator - Detect development acceleration opportunities.

Scans GitHub events (PR merges, issue opens, artifact changes) and extracts
actionable opportunities for follow-up work.

Exit Codes (ADR-035):
    0 - Success, opportunities detected and output
    1 - Success, no opportunities found
    2 - Configuration or input error

Standards:
    - ADR-006: Business logic in scripts, not workflow YAML
    - ADR-042: Python-first for new scripts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class EventType(StrEnum):
    """GitHub event types that trigger opportunity detection."""

    PR_MERGED = "pull_request_merged"
    ISSUE_OPENED = "issue_opened"
    ISSUE_LABELED = "issue_labeled"
    ARTIFACT_PUSH = "artifact_push"
    SCHEDULED = "scheduled"


class OpportunityType(StrEnum):
    """Categories of detected velocity opportunities."""

    TODO_FOLLOWUP = "todo_followup"
    FIXME_FOLLOWUP = "fixme_followup"
    STALE_ISSUE = "stale_issue"
    NEW_ARTIFACT = "new_artifact"
    COMPLEXITY_TRIAGE = "complexity_triage"
    AGENT_ROUTING = "agent_routing"


@dataclass
class Opportunity:
    """A detected velocity opportunity."""

    opportunity_type: str
    title: str
    description: str
    source_event: str
    source_ref: str
    suggested_agent: str = ""
    priority: str = "medium"
    metadata: dict[str, str] = field(default_factory=dict)


# Patterns to detect in changed files
TODO_PATTERN = re.compile(
    r"^\+.*\b(TODO|FIXME|HACK|XXX|FOLLOW[- ]?UP)\b[:\s]*(.*)",
    re.IGNORECASE | re.MULTILINE,
)

COMPLEXITY_KEYWORDS = {
    "high": [
        "architecture",
        "migration",
        "breaking change",
        "security",
        "performance",
        "refactor",
        "redesign",
    ],
    "medium": [
        "feature",
        "enhancement",
        "integration",
        "workflow",
        "automation",
    ],
    "low": [
        "bug",
        "fix",
        "typo",
        "documentation",
        "update",
        "chore",
    ],
}

AGENT_KEYWORDS: dict[str, list[str]] = {
    "agent-security": ["security", "vulnerability", "cve", "auth", "credential", "secret"],
    "agent-architect": ["architecture", "adr", "design", "pattern", "structure"],
    "agent-devops": ["ci", "cd", "pipeline", "workflow", "deploy", "action"],
    "agent-implementer": ["implement", "code", "develop", "build", "create"],
    "agent-qa": ["test", "coverage", "quality", "verify", "validate"],
    "agent-analyst": ["investigate", "research", "analyze", "benchmark"],
    "agent-planner": ["plan", "milestone", "epic", "roadmap", "schedule"],
    "agent-explainer": ["document", "explain", "prd", "guide", "readme"],
}


def get_pr_diff(pr_number: int) -> str:
    """Fetch the diff for a merged PR using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "--color=never"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def extract_todos_from_diff(diff: str, pr_number: int) -> list[Opportunity]:
    """Extract TODO/FIXME patterns from a PR diff."""
    opportunities: list[Opportunity] = []
    current_file = ""

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            current_file = parts[1] if len(parts) > 1 else ""
            continue

        match = TODO_PATTERN.match(line)
        if match:
            tag = match.group(1).upper()
            comment = match.group(2).strip()
            opp_type = (
                OpportunityType.FIXME_FOLLOWUP
                if tag == "FIXME"
                else OpportunityType.TODO_FOLLOWUP
            )
            opportunities.append(
                Opportunity(
                    opportunity_type=opp_type,
                    title=f"{tag} in {current_file or 'unknown file'}: {comment[:80]}",
                    description=(
                        f"Found `{tag}` comment in merged PR #{pr_number}:\n"
                        f"File: `{current_file}`\n"
                        f"Comment: {comment}"
                    ),
                    source_event=EventType.PR_MERGED,
                    source_ref=f"PR #{pr_number}",
                    suggested_agent="task-generator",
                    priority="medium",
                    metadata={"file": current_file, "tag": tag, "pr_number": str(pr_number)},
                )
            )

    return opportunities


def score_issue_complexity(title: str, body: str) -> str:
    """Score issue complexity based on keyword analysis."""
    text = f"{title} {body}".lower()

    for level, keywords in COMPLEXITY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return level

    return "medium"


def suggest_agents(title: str, body: str) -> list[str]:
    """Suggest agent routing based on issue content."""
    text = f"{title} {body}".lower()
    suggested: list[str] = []

    for agent, keywords in AGENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                suggested.append(agent)
                break

    return suggested


def process_issue_opened(
    issue_number: int,
    title: str,
    body: str,
) -> list[Opportunity]:
    """Process a newly opened issue for triage opportunities."""
    opportunities: list[Opportunity] = []

    complexity = score_issue_complexity(title, body)
    agents = suggest_agents(title, body)

    opportunities.append(
        Opportunity(
            opportunity_type=OpportunityType.COMPLEXITY_TRIAGE,
            title=f"Triage issue #{issue_number}: {title[:60]}",
            description=(
                f"New issue opened with {complexity} complexity.\n"
                f"Suggested agents: {', '.join(agents) if agents else 'none detected'}"
            ),
            source_event=EventType.ISSUE_OPENED,
            source_ref=f"Issue #{issue_number}",
            suggested_agent=agents[0] if agents else "orchestrator",
            priority="high" if complexity == "high" else "medium",
            metadata={
                "complexity": complexity,
                "suggested_agents": ",".join(agents),
                "issue_number": str(issue_number),
            },
        )
    )

    if agents:
        opportunities.append(
            Opportunity(
                opportunity_type=OpportunityType.AGENT_ROUTING,
                title=f"Route issue #{issue_number} to {', '.join(agents)}",
                description=(
                    f"Issue content suggests routing to: {', '.join(agents)}\n"
                    f"Complexity: {complexity}"
                ),
                source_event=EventType.ISSUE_OPENED,
                source_ref=f"Issue #{issue_number}",
                suggested_agent=agents[0],
                priority="low",
                metadata={
                    "agents": ",".join(agents),
                    "issue_number": str(issue_number),
                },
            )
        )

    return opportunities


def detect_artifact_changes(changed_files: Sequence[str]) -> list[Opportunity]:
    """Detect opportunities from changes to agent artifacts."""
    opportunities: list[Opportunity] = []

    for filepath in changed_files:
        path = Path(filepath)
        if not str(path).startswith(".agents/"):
            continue

        parts = path.parts
        if len(parts) < 2:
            continue

        artifact_dir = parts[1]
        filename = path.name

        if artifact_dir == "architecture" and filename.startswith("ADR-"):
            opportunities.append(
                Opportunity(
                    opportunity_type=OpportunityType.NEW_ARTIFACT,
                    title=f"New/updated ADR: {filename}",
                    description=f"ADR changed at `{filepath}`. Ensure implementation plan exists.",
                    source_event=EventType.ARTIFACT_PUSH,
                    source_ref=filepath,
                    suggested_agent="planner",
                    priority="high",
                    metadata={"artifact_type": "adr", "file": filepath},
                )
            )
        elif artifact_dir == "planning":
            opportunities.append(
                Opportunity(
                    opportunity_type=OpportunityType.NEW_ARTIFACT,
                    title=f"Planning doc updated: {filename}",
                    description=f"Planning document at `{filepath}` was updated. Queue for review.",
                    source_event=EventType.ARTIFACT_PUSH,
                    source_ref=filepath,
                    suggested_agent="critic",
                    priority="medium",
                    metadata={"artifact_type": "planning", "file": filepath},
                )
            )
        elif artifact_dir == "skills":
            opportunities.append(
                Opportunity(
                    opportunity_type=OpportunityType.NEW_ARTIFACT,
                    title=f"Skill updated: {filename}",
                    description=f"Skill artifact at `{filepath}` was updated.",
                    source_event=EventType.ARTIFACT_PUSH,
                    source_ref=filepath,
                    suggested_agent="skillbook",
                    priority="low",
                    metadata={"artifact_type": "skill", "file": filepath},
                )
            )

    return opportunities


def get_changed_files_from_push() -> list[str]:
    """Get list of changed files from the most recent push."""
    before_sha = os.environ.get("GITHUB_EVENT_BEFORE", "")
    after_sha = os.environ.get("GITHUB_SHA", "HEAD")

    if not before_sha:
        return []

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", before_sha, after_sha],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return []


def detect_opportunities(
    event_name: str,
    event_action: str = "",
    pr_number: int = 0,
    pr_merged: bool = False,
    issue_number: int = 0,
    issue_title: str = "",
    issue_body: str = "",
    changed_files: Sequence[str] | None = None,
) -> list[Opportunity]:
    """Main entry point: detect opportunities based on the GitHub event."""
    opportunities: list[Opportunity] = []

    if event_name == "pull_request" and event_action == "closed" and pr_merged and pr_number > 0:
        diff = get_pr_diff(pr_number)
        if diff:
            opportunities.extend(extract_todos_from_diff(diff, pr_number))

    elif event_name == "issues" and event_action in ("opened", "labeled"):
        if issue_number > 0 and issue_title:
            opportunities.extend(
                process_issue_opened(issue_number, issue_title, issue_body)
            )

    elif event_name == "push":
        files = list(changed_files) if changed_files else get_changed_files_from_push()
        agent_files = [f for f in files if f.startswith(".agents/")]
        if agent_files:
            opportunities.extend(detect_artifact_changes(agent_files))

    return opportunities


def build_args_from_env() -> list[str]:
    """Build CLI arguments from GitHub Actions environment variables."""
    args: list[str] = []
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    if not event_name:
        return args

    args.extend(["--event", event_name])

    if event_path and Path(event_path).is_file():
        try:
            with open(event_path) as f:
                event_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return args

        action = event_data.get("action", "")
        if action:
            args.extend(["--action", action])

        if event_name == "pull_request":
            pr = event_data.get("pull_request", {})
            pr_num = pr.get("number", 0)
            if pr_num:
                args.extend(["--pr-number", str(pr_num)])
            if pr.get("merged", False):
                args.append("--pr-merged")

        elif event_name == "issues":
            issue = event_data.get("issue", {})
            issue_num = issue.get("number", 0)
            if issue_num:
                args.extend(["--issue-number", str(issue_num)])
            title = issue.get("title", "")
            if title:
                args.extend(["--issue-title", title])
            body = issue.get("body", "") or ""
            if body:
                args.extend(["--issue-body", body])

    return args


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Velocity Accelerator - Detect development acceleration opportunities",
    )
    parser.add_argument(
        "--event",
        required=True,
        help="GitHub event name (pull_request, issues, push, schedule)",
    )
    parser.add_argument(
        "--action",
        default="",
        help="Event action (closed, opened, labeled)",
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        default=0,
        help="Pull request number",
    )
    parser.add_argument(
        "--pr-merged",
        action="store_true",
        help="Whether the PR was merged",
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        default=0,
        help="Issue number",
    )
    parser.add_argument(
        "--issue-title",
        default="",
        help="Issue title",
    )
    parser.add_argument(
        "--issue-body",
        default="",
        help="Issue body",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="List of changed files (for push events)",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "summary"],
        default="json",
        help="Output format",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect event from GitHub Actions environment",
    )

    if argv is not None:
        return parser.parse_args(argv)

    # If --auto is the only arg, build from env
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        env_args = build_args_from_env()
        if not env_args:
            parser.error("--auto specified but no GitHub event environment found")
        return parser.parse_args(env_args)

    return parser.parse_args()


def format_summary(opportunities: list[Opportunity]) -> str:
    """Format opportunities as a human-readable summary."""
    if not opportunities:
        return "No velocity opportunities detected."

    lines = [f"## 🚀 Velocity Accelerator: {len(opportunities)} Opportunities Detected\n"]

    for i, opp in enumerate(opportunities, 1):
        lines.append(f"### {i}. {opp.title}")
        lines.append(f"- **Type**: {opp.opportunity_type}")
        lines.append(f"- **Priority**: {opp.priority}")
        lines.append(f"- **Source**: {opp.source_ref}")
        if opp.suggested_agent:
            lines.append(f"- **Suggested Agent**: {opp.suggested_agent}")
        lines.append(f"- {opp.description}")
        lines.append("")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    opportunities = detect_opportunities(
        event_name=args.event,
        event_action=args.action,
        pr_number=args.pr_number,
        pr_merged=args.pr_merged,
        issue_number=args.issue_number,
        issue_title=args.issue_title,
        issue_body=args.issue_body,
        changed_files=args.changed_files,
    )

    if args.output_format == "json":
        output = json.dumps([asdict(o) for o in opportunities], indent=2)
        print(output)
    else:
        print(format_summary(opportunities))

    return 0 if opportunities else 1


if __name__ == "__main__":
    sys.exit(main())
