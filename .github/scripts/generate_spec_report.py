#!/usr/bin/env python3
"""Generate the spec-to-implementation validation report.

Input env vars (used as defaults for CLI args):
    HAS_SPECS              - Whether PR references specs ('true' or other)
    SPEC_REFS              - Space-separated spec reference IDs
    ISSUE_REFS             - Space-separated issue references
    TRACE_VERDICT          - Verdict from traceability check
    TRACE_FINDINGS         - Findings from traceability check
    COMPLETENESS_VERDICT   - Verdict from completeness check
    COMPLETENESS_FINDINGS  - Findings from completeness check
    TRACE_INFRA_FAILURE        - Whether trace failure was infrastructure-related
    COMPLETENESS_INFRA_FAILURE - Whether completeness failure was infrastructure-related
    GITHUB_REPOSITORY      - Owner/repo slug
    SERVER_URL             - GitHub server URL
    RUN_ID                 - Current workflow run ID
    EVENT_NAME             - Triggering event name
    REF_NAME               - Git ref name
    GITHUB_OUTPUT          - Path to GitHub Actions output file
    GITHUB_WORKSPACE       - Workspace root (for package imports)
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
    get_verdict_alert_type,
    get_verdict_emoji,
    initialize_ai_review,
    spec_validation_failed,
    write_output,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate the spec-to-implementation validation report.",
    )
    parser.add_argument(
        "--has-specs",
        default=os.environ.get("HAS_SPECS", ""),
        help="Whether PR references specs ('true' or other)",
    )
    parser.add_argument(
        "--spec-refs",
        default=os.environ.get("SPEC_REFS", ""),
        help="Space-separated spec reference IDs",
    )
    parser.add_argument(
        "--issue-refs",
        default=os.environ.get("ISSUE_REFS", ""),
        help="Space-separated issue references",
    )
    parser.add_argument(
        "--trace-verdict",
        default=os.environ.get("TRACE_VERDICT", ""),
        help="Verdict from traceability check",
    )
    parser.add_argument(
        "--trace-findings",
        default=os.environ.get("TRACE_FINDINGS", ""),
        help="Findings from traceability check",
    )
    parser.add_argument(
        "--completeness-verdict",
        default=os.environ.get("COMPLETENESS_VERDICT", ""),
        help="Verdict from completeness check",
    )
    parser.add_argument(
        "--completeness-findings",
        default=os.environ.get("COMPLETENESS_FINDINGS", ""),
        help="Findings from completeness check",
    )
    parser.add_argument(
        "--trace-infra-failure",
        default=os.environ.get("TRACE_INFRA_FAILURE", ""),
        help="Whether trace failure was infrastructure-related",
    )
    parser.add_argument(
        "--completeness-infra-failure",
        default=os.environ.get("COMPLETENESS_INFRA_FAILURE", ""),
        help="Whether completeness failure was infrastructure-related",
    )
    parser.add_argument(
        "--github-repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Owner/repo slug",
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("SERVER_URL", ""),
        help="GitHub server URL",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("RUN_ID", ""),
        help="Current workflow run ID",
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
    return parser


def _is_infra_failure(flag: str) -> bool:
    """Return True only when the structured infrastructure flag is set.

    Duplicates ``check_spec_failures.py``'s helper of the same name rather
    than moving it into ``scripts.ai_review_common``: that module's
    ``verdict.py`` is pinned by a 100% branch-coverage gate and loaded
    standalone by file path from a vendored plugin probe
    (``tests/e2e/test_vendored_review_e2e.py``), so a new export there costs
    more review surface than one three-line predicate duplicated across two
    call sites justifies.
    """
    return flag.lower() in ("true", "1", "yes")


def _findings_section(is_infra: bool, findings: str) -> str:
    """Return a side's findings body, labeled when that side is infra-flagged.

    The raw Copilot CLI output stays visible: dropping it loses observability
    on this fail-open path (issue #5738). An infra-flagged side's raw verdict
    (typically `CRITICAL_FAIL`) describes a process that never completed, not
    a code-quality judgement, so it is prefixed with a label stating the
    check did not run, and that the text below is unevaluated output, not a
    verdict.
    """
    if not is_infra:
        return findings
    return (
        "> [!NOTE]\n"
        "> This check did not run (infrastructure failure). The raw Copilot "
        "CLI output follows, unevaluated:\n"
        "\n"
        f"{findings}"
    )


def _build_no_specs_report(repository: str) -> str:
    """Build the warning report when no spec references are found."""
    return f"""\
<!-- AI-SPEC-VALIDATION -->

## Spec-to-Implementation Validation

> [!WARNING]
> **No spec references found**
>
> This PR does not reference any specifications (REQ-*, DESIGN-*, TASK-*, or linked issues).

<details>
<summary>How to add spec references</summary>

Add spec references to your PR description to enable traceability:

| Method | Example |
|:-------|:--------|
| Reference requirements | `Implements REQ-001` |
| Link issues | `Closes #123` |
| Reference spec files | `.project-toolkit/specs/requirements/...` |

**Spec Requirement by PR Type:**

| PR Type | Required? |
|:--------|:----------|
| Feature (`feat:`) | Required |
| Bug fix (`fix:`) | Optional |
| Refactor (`refactor:`) | Optional |
| Documentation (`docs:`) | Not required |
| Infrastructure (`ci:`, `build:`, `chore:`) | Optional |

See PR template for full guidance.

</details>

---

<sub>Powered by [AI Spec Validator](https://github.com/{repository}) workflow</sub>"""


def _build_full_report(
    final_verdict: str,
    trace_verdict: str,
    completeness_verdict: str,
    trace_infra: bool,
    completeness_infra: bool,
    spec_refs: str,
    issue_refs: str,
    trace_findings: str,
    completeness_findings: str,
    repository: str,
    server_url: str,
    run_id: str,
    event_name: str,
    ref_name: str,
) -> str:
    """Build the full validation report with all check results.

    An infra-failed side's summary-table cell and final verdict never show
    its raw AI-review verdict (typically `CRITICAL_FAIL`): that verdict
    describes a Copilot CLI process that never completed, not a code-quality
    judgement. The raw text is still shown in that side's details block
    (`_findings_section`), so the fail-open path keeps its observability, but
    labeled so it reads as unevaluated output, not a verdict (issue #5738).
    """
    if final_verdict == "INFRA_FAILURE":
        alert_type = "WARNING"
        final_emoji = "⚠️"
    else:
        alert_type = get_verdict_alert_type(final_verdict)
        final_emoji = get_verdict_emoji(final_verdict)

    trace_display = "INFRA_FAILURE (did not run)" if trace_infra else trace_verdict
    completeness_display = (
        "INFRA_FAILURE (did not run)" if completeness_infra else completeness_verdict
    )
    trace_emoji = "⚠️" if trace_infra else get_verdict_emoji(trace_verdict)
    completeness_emoji = (
        "⚠️" if completeness_infra else get_verdict_emoji(completeness_verdict)
    )

    infra_note = ""
    if trace_infra or completeness_infra:
        if final_verdict == "FAIL":
            # One side is infra-flagged, but the other side genuinely failed
            # (spec_validation_failed still returned True): that FAIL blocks
            # merge, so the note must not say otherwise (issue #5738 follow-up).
            infra_note = """
> [!WARNING]
> **Infrastructure failure on one side; the other side's FAIL is real.** A
> check marked `INFRA_FAILURE (did not run)` below contributed no verdict:
> Copilot CLI failed after retries and never evaluated that side of this PR.
> The **Final Verdict: FAIL** above comes from the side that did run, and it
> blocks merge under normal policy. If the infrastructure failure persists,
> check `COPILOT_GITHUB_TOKEN` scope, rate limits, or network connectivity.
"""
        else:
            infra_note = """
> [!WARNING]
> **Infrastructure failure detected.** A check marked `INFRA_FAILURE (did not run)`
> below is not a code-quality result: Copilot CLI failed after retries and never
> evaluated this PR. Per current policy this does not block merge (see
> `.agents/governance/FAIL-OPEN-INVENTORY.md`). If this persists, check
> `COPILOT_GITHUB_TOKEN` scope, rate limits, or network connectivity.
"""

    trace_findings_body = _findings_section(trace_infra, trace_findings)
    completeness_findings_body = _findings_section(completeness_infra, completeness_findings)

    return f"""\
<!-- AI-SPEC-VALIDATION -->

## Spec-to-Implementation Validation

> [!{alert_type}]
> {final_emoji} **Final Verdict: {final_verdict}**
{infra_note}
<details>
<summary>What is Spec Validation?</summary>

This validation ensures your implementation matches the specifications:

- **Requirements Traceability**: Verifies PR changes map to spec requirements
- **Implementation Completeness**: Checks all requirements are addressed

</details>

### Validation Summary

| Check | Verdict | Status |
|:------|:--------|:------:|
| Requirements Traceability | `{trace_display}` | {trace_emoji} |
| Implementation Completeness | `{completeness_display}` | {completeness_emoji} |

### Spec References

| Type | References |
|:-----|:-----------|
| **Specs** | {spec_refs} |
| **Issues** | {issue_refs} |

<details>
<summary>Requirements Traceability Details</summary>

{trace_findings_body}

</details>

<details>
<summary>Implementation Completeness Details</summary>

{completeness_findings_body}

</details>

---

<details>
<summary>Run Details</summary>

| Property | Value |
|:---------|:------|
| **Run ID** | [{run_id}]({server_url}/{repository}/actions/runs/{run_id}) |
| **Triggered by** | `{event_name}` on `{ref_name}` |

</details>

<sub>Powered by [AI Spec Validator](https://github.com/{repository}) workflow</sub>"""


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    has_specs: str = args.has_specs
    repository: str = args.github_repository

    report_dir = initialize_ai_review()
    report_file = os.path.join(report_dir, "spec-validation-report.md")

    if has_specs != "true":
        report = _build_no_specs_report(repository)
    else:
        trace_verdict: str = args.trace_verdict
        completeness_verdict: str = args.completeness_verdict
        trace_infra: bool = _is_infra_failure(args.trace_infra_failure)
        completeness_infra: bool = _is_infra_failure(args.completeness_infra_failure)

        if trace_infra and completeness_infra:
            # Neither side produced a real verdict; nothing here is PASS,
            # FAIL, or WARN. Mirrors check_spec_failures.py's own
            # both-infra branch, which likewise never reaches
            # spec_validation_failed on raw CRITICAL_FAIL verdicts.
            final_verdict = "INFRA_FAILURE"
        else:
            trace_for_verdict = "" if trace_infra else trace_verdict
            completeness_for_verdict = (
                "" if completeness_infra else completeness_verdict
            )
            if spec_validation_failed(trace_for_verdict, completeness_for_verdict):
                final_verdict = "FAIL"
            elif trace_infra or completeness_infra:
                # One side could not run; the other side did not fail, but
                # only half of validation completed. WARN says "not fully
                # validated," which PASS would not.
                final_verdict = "WARN"
            elif trace_verdict == "WARN" or completeness_verdict == "WARN":
                final_verdict = "WARN"
            else:
                final_verdict = "PASS"

        spec_refs: str = args.spec_refs or "*None*"
        issue_refs: str = args.issue_refs or "*None*"
        trace_findings: str = args.trace_findings or "No traceability output"
        completeness_findings: str = (
            args.completeness_findings or "No completeness output"
        )

        server_url: str = args.server_url
        run_id: str = args.run_id
        event_name: str = args.event_name
        ref_name: str = args.ref_name

        report = _build_full_report(
            final_verdict=final_verdict,
            trace_verdict=trace_verdict,
            completeness_verdict=completeness_verdict,
            trace_infra=trace_infra,
            completeness_infra=completeness_infra,
            spec_refs=spec_refs,
            issue_refs=issue_refs,
            trace_findings=trace_findings,
            completeness_findings=completeness_findings,
            repository=repository,
            server_url=server_url,
            run_id=run_id,
            event_name=event_name,
            ref_name=ref_name,
        )

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    write_output("report_file", report_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
