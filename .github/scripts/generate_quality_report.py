#!/usr/bin/env python3
"""Generate the PR quality gate markdown report from aggregated agent verdicts.

Input env vars (used as defaults for CLI args):
    RUN_ID, SERVER_URL, REPOSITORY, EVENT_NAME, REF_NAME, SHA
    FINAL_VERDICT
    SECURITY_VERDICT, QA_VERDICT, ANALYST_VERDICT,
    ARCHITECT_VERDICT, DEVOPS_VERDICT, ROADMAP_VERDICT
    SECURITY_CATEGORY, QA_CATEGORY, ANALYST_CATEGORY,
    ARCHITECT_CATEGORY, DEVOPS_CATEGORY, ROADMAP_CATEGORY
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import argparse
import os
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import (  # noqa: E402
    FAIL_VERDICTS,
    get_verdict_alert_type,
    get_verdict_emoji,
    initialize_ai_review,
    write_output,
)

_AGENTS = ("security", "qa", "analyst", "architect", "devops", "roadmap")

_AGENT_DISPLAY_NAMES = {
    "security": "Security",
    "qa": "QA",
    "analyst": "Analyst",
    "architect": "Architect",
    "devops": "DevOps",
    "roadmap": "Roadmap",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate the PR quality gate markdown report from aggregated agent verdicts.",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("RUN_ID", ""),
        help="GitHub Actions run ID",
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("SERVER_URL", ""),
        help="GitHub server URL",
    )
    parser.add_argument(
        "--repository",
        default=os.environ.get("REPOSITORY", ""),
        help="Repository in owner/repo format",
    )
    parser.add_argument(
        "--event-name",
        default=os.environ.get("EVENT_NAME", ""),
        help="Triggering event name",
    )
    parser.add_argument(
        "--ref-name",
        default=os.environ.get("REF_NAME", ""),
        help="Git ref name",
    )
    parser.add_argument(
        "--sha",
        default=os.environ.get("SHA", ""),
        help="Git commit SHA",
    )
    parser.add_argument(
        "--final-verdict",
        default=os.environ.get("FINAL_VERDICT", ""),
        help="Final aggregated verdict",
    )
    for agent in _AGENTS:
        upper = agent.upper()
        parser.add_argument(
            f"--{agent}-verdict",
            default=os.environ.get(f"{upper}_VERDICT", ""),
            help=f"{agent.capitalize()} agent verdict",
        )
        parser.add_argument(
            f"--{agent}-category",
            default=os.environ.get(f"{upper}_CATEGORY", ""),
            help=f"{agent.capitalize()} failure category",
        )
    parser.add_argument(
        "--pr-author",
        default=os.environ.get("PR_AUTHOR", ""),
        help="PR author login for @mention notifications on actionable verdicts",
    )
    return parser


def _build_action_required_section(
    pr_author: str,
    final_verdict: str,
    verdicts: dict[str, str],
) -> str:
    """Build an action-required section that @mentions the PR author.

    Only emits content when actionable verdicts (CRITICAL_FAIL, FAIL, etc.) exist.
    """
    if not pr_author:
        return ""

    actionable_agents = [
        _AGENT_DISPLAY_NAMES[agent]
        for agent in _AGENTS
        if verdicts.get(agent, "") in FAIL_VERDICTS
    ]
    if not actionable_agents:
        return ""

    lines = [
        "",
        "### Action Required",
        "",
        f"@{pr_author}, this PR has findings that need your attention:",
        "",
    ]
    for agent_name in actionable_agents:
        lines.append(f"- **{agent_name}** review flagged issues")
    lines.append("")
    lines.append(
        "Please review the agent findings above and push fixes or reply with justification."
    )
    lines.append("")
    return "\n".join(lines)


def _build_findings_sections() -> str:
    """Read findings files for each agent and build collapsible sections."""
    sections = ""
    for agent in _AGENTS:
        title = f"{_AGENT_DISPLAY_NAMES[agent]} Review Details"
        findings_file = f"ai-review-results/{agent}-findings.txt"

        if os.path.isfile(findings_file):
            try:
                with open(findings_file, encoding="utf-8") as f:
                    findings = f.read()
                if findings:
                    sections += (
                        f"\n<details>\n<summary>{title}</summary>"
                        f"\n\n{findings}\n\n</details>\n"
                    )
                else:
                    sections += (
                        f"\n<details>\n<summary>{title}</summary>"
                        "\n\n\u26a0\ufe0f No findings available (empty file)\n\n</details>\n"
                    )
            except OSError as exc:
                print(f"::error::Failed to read findings file for {agent}: {exc}")
                sections += (
                    f"\n<details>\n<summary>{title}</summary>"
                    f"\n\n\u274c Error reading findings file: {exc}\n\n</details>\n"
                )
        else:
            sections += (
                f"\n<details>\n<summary>{title}</summary>"
                "\n\n\u26a0\ufe0f Findings file not found (agent review may have failed)"
                "\n\n</details>\n"
            )

    return sections


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    report_dir = initialize_ai_review()
    if not os.path.isdir(report_dir):
        print(f"::error::Failed to initialize AI review directory: {report_dir}")
        return 1

    report_file = os.path.join(report_dir, "pr-quality-report.md")

    run_id: str = args.run_id
    server_url: str = args.server_url
    repository: str = args.repository
    event_name: str = args.event_name
    ref_name: str = args.ref_name
    sha: str = args.sha
    final_verdict: str = args.final_verdict

    pr_author: str = args.pr_author

    verdicts: dict[str, str] = {}
    categories: dict[str, str] = {}
    emojis: dict[str, str] = {}
    for agent in _AGENTS:
        verdicts[agent] = getattr(args, f"{agent}_verdict")
        categories[agent] = getattr(args, f"{agent}_category")
        emojis[agent] = get_verdict_emoji(verdicts[agent])

    alert_type = get_verdict_alert_type(final_verdict)
    final_emoji = get_verdict_emoji(final_verdict)

    lines = [
        "<!-- AI-PR-QUALITY-GATE -->",
        "",
        "## AI Quality Gate Review",
        "",
        f"> [!{alert_type}]",
        f"> {final_emoji} **Final Verdict: {final_verdict}**",
        "",
        "<details>",
        "<summary>Walkthrough</summary>",
        "",
        "This PR was reviewed by six AI agents **in parallel**,"
        " analyzing different aspects of the changes:",
        "",
        "- **Security Agent**: Scans for vulnerabilities, secrets exposure,"
        " and security anti-patterns",
        "- **QA Agent**: Evaluates test coverage, error handling, and code quality",
        "- **Analyst Agent**: Assesses code quality, impact analysis,"
        " and maintainability",
        "- **Architect Agent**: Reviews design patterns, system boundaries,"
        " and architectural concerns",
        "- **DevOps Agent**: Evaluates CI/CD, build pipelines, and infrastructure changes",
        "- **Roadmap Agent**: Assesses strategic alignment, feature scope, and user value",
        "",
        "</details>",
        "",
        "### Review Summary",
        "",
        "| Agent | Verdict | Category | Status |",
        "|:------|:--------|:---------|:------:|",
    ]

    for agent in _AGENTS:
        display = _AGENT_DISPLAY_NAMES[agent]
        lines.append(
            f"| {display} | {verdicts[agent]} | {categories[agent]} | {emojis[agent]} |"
        )

    lines.append("")
    lines.append(
        f'\U0001f4a1 **Quick Access**: Click on individual agent jobs '
        f'(e.g., "\U0001f512 security Review", "\U0001f9ea qa Review") '
        f"in the [workflow run]({server_url}/{repository}/actions/runs/{run_id}) "
        f"to see detailed findings and step summaries."
    )
    lines.append("")

    report = "\n".join(lines)
    report += _build_action_required_section(pr_author, final_verdict, verdicts)
    report += _build_findings_sections()

    footer_lines = [
        "",
        "---",
        "",
        "<details>",
        "<summary>Run Details</summary>",
        "",
        "| Property | Value |",
        "|:---------|:------|",
        f"| **Run ID** | [{run_id}]({server_url}/{repository}/actions/runs/{run_id}) |",
        f"| **Triggered by** | `{event_name}` on `{ref_name}` |",
        f"| **Commit** | `{sha}` |",
        "",
        "</details>",
        "",
        f"<sub>Powered by [AI Quality Gate](https://github.com/{repository}) workflow</sub>",
    ]
    report += "\n".join(footer_lines)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    write_output("report_file", report_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
