#!/usr/bin/env python3
"""Generate a session protocol compliance report in markdown.

Replaces the inline PowerShell block in the 'Generate Compliance Report'
step (id: report) of ai-session-protocol.yml.

Input env vars:
    OVERALL_VERDICT    - Aggregated verdict from the aggregate step
    MUST_FAILURES      - Total count of MUST requirement failures
    GITHUB_REPOSITORY  - Repository in owner/repo format
    SERVER_URL         - GitHub server URL
    RUN_ID             - GitHub Actions run ID
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import os
import sys
from glob import glob

# Add workspace root to Python path for package imports
workspace = os.environ.get("GITHUB_WORKSPACE", ".")
sys.path.insert(0, workspace)

from scripts.ai_review_common import (  # noqa: E402
    get_verdict_alert_type,
    get_verdict_emoji,
    initialize_ai_review,
)


def write_output(key: str, value: str) -> None:
    """Append a key=value line to the GitHub Actions output file."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{key}={value}\n")


def main() -> None:
    overall_verdict = os.environ.get("OVERALL_VERDICT", "PASS")
    must_failures = os.environ.get("MUST_FAILURES", "0")
    github_repository = os.environ.get("GITHUB_REPOSITORY", "")
    server_url = os.environ.get("SERVER_URL", "")
    run_id = os.environ.get("RUN_ID", "")

    report_dir = initialize_ai_review()
    report_file = os.path.join(report_dir, "session-compliance-report.md")

    alert_type = get_verdict_alert_type(overall_verdict)
    emoji = get_verdict_emoji(overall_verdict)

    # Build verdict message
    if int(must_failures) > 0:
        verdict_msg = (
            f"{must_failures} MUST requirement(s) not met."
            " These must be addressed before merge."
        )
    else:
        verdict_msg = "All session protocol requirements satisfied."

    # Count files checked
    verdict_files = sorted(glob("validation-results/*-verdict.txt"))
    files_checked = len(verdict_files)

    # Build report header
    report = f"""\
<!-- AI-SESSION-PROTOCOL -->

## Session Protocol Compliance Report

> [!{alert_type}]
> {emoji} **Overall Verdict: {overall_verdict}**
>
> {verdict_msg}

<details>
<summary>What is Session Protocol?</summary>

Session logs document agent work sessions and must comply with RFC 2119 requirements:

- **MUST**: Required for compliance (blocking failures)
- **SHOULD**: Recommended practices (warnings)
- **MAY**: Optional enhancements

See [`.agents/SESSION-PROTOCOL.md`](.agents/SESSION-PROTOCOL.md) for full specification.

</details>

### Compliance Summary

| Session File | Verdict | MUST Failures |
|:-------------|:--------|:-------------:|
"""

    # Add summary row for each session file
    for verdict_file in verdict_files:
        basename = os.path.basename(verdict_file)
        name = basename.replace("-verdict.txt", "")

        with open(verdict_file) as f:
            verdict = f.read().strip()

        must_file = f"validation-results/{name}-must-failures.txt"
        if os.path.exists(must_file):
            with open(must_file) as f:
                must_count = f.read().strip()
        else:
            must_count = "0"

        row_emoji = get_verdict_emoji(verdict)
        report += f"| `{name}.md` | {row_emoji} {verdict} | {must_count} |\n"

    # Add detailed findings
    report += "\n### Detailed Validation Results\n"
    report += (
        "\nClick each session to see the complete validation report"
        " with specific requirement failures.\n"
    )

    findings_files = sorted(glob("validation-results/*-findings.txt"))
    for findings_file in findings_files:
        basename = os.path.basename(findings_file)
        name = basename.replace("-findings.txt", "")

        with open(findings_file) as f:
            findings = f.read()

        report += f"\n<details>\n<summary>\U0001f4c4 {name}</summary>\n\n"
        report += findings
        report += "\n</details>\n"

    # Add footer
    report += f"""
---

<details>
<summary>\u2728 Zero-Token Validation</summary>

This validation uses deterministic PowerShell script analysis instead of AI:

- \u2705 **Zero tokens consumed** (previously 300K-900K per debug cycle)
- \u2705 **Instant feedback** - see exact failures in this summary
- \u2705 **No artifact downloads** needed to diagnose issues
- \u2705 **10x-100x faster** debugging

Powered by [`validate_session_json.py`](../../scripts/validate_session_json.py)

</details>

<details>
<summary>\U0001f4ca Run Details</summary>

| Property | Value |
|:---------|:------|
| **Run ID** | [{run_id}]({server_url}/{github_repository}/actions/runs/{run_id}) |
| **Files Checked** | {files_checked} |
| **Validation Method** | Deterministic script analysis |

</details>

<sub>Powered by [Session Protocol Validator](https://github.com/{github_repository}) workflow</sub>
"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    write_output("report_file", report_file)


if __name__ == "__main__":
    main()
