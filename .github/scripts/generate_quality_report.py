#!/usr/bin/env python3
"""Generate the PR quality gate markdown report from aggregated agent verdicts.

Input env vars:
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

import os
import sys

workspace = os.environ.get("GITHUB_WORKSPACE", ".")
sys.path.insert(0, workspace)

from scripts.ai_review_common import (  # noqa: E402
    get_verdict_alert_type,
    get_verdict_emoji,
    initialize_ai_review,
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



def write_output(key: str, value: str) -> None:
    """Append a key=value line to the GitHub Actions output file."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


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


def main() -> None:
    report_dir = initialize_ai_review()
    if not os.path.isdir(report_dir):
        print(f"::error::Failed to initialize AI review directory: {report_dir}")
        sys.exit(1)

    report_file = os.path.join(report_dir, "pr-quality-report.md")

    run_id = os.environ.get("RUN_ID", "")
    server_url = os.environ.get("SERVER_URL", "")
    repository = os.environ.get("REPOSITORY", "")
    event_name = os.environ.get("EVENT_NAME", "")
    ref_name = os.environ.get("REF_NAME", "")
    sha = os.environ.get("SHA", "")
    final_verdict = os.environ.get("FINAL_VERDICT", "")

    verdicts: dict[str, str] = {}
    categories: dict[str, str] = {}
    emojis: dict[str, str] = {}
    for agent in _AGENTS:
        verdicts[agent] = os.environ.get(f"{agent.upper()}_VERDICT", "")
        categories[agent] = os.environ.get(f"{agent.upper()}_CATEGORY", "")
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


if __name__ == "__main__":
    main()
