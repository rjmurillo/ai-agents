#!/usr/bin/env python3
"""Build the PR validation report and write workflow outputs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

CONFIG_ERROR = 2
REPORT_PATH = Path("pr-validation-report.md")


def _resolve_output_path() -> Path | None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return None
    return Path(output_path)


def _append_output(output_path: Path, name: str, value: str) -> None:
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def _status_inputs() -> dict[str, str]:
    return {
        "description": os.environ.get("DESCRIPTION_RESULT") or "ERROR",
        "bypass_used": os.environ.get("BYPASS_USED", ""),
        "bypass_label": os.environ.get("BYPASS_LABEL", ""),
        "bypass_count": os.environ.get("BYPASS_COUNT", ""),
        "keywords": os.environ.get("KEYWORDS_STATUS", ""),
        "template": os.environ.get("TEMPLATE_STATUS", ""),
        "template_message": os.environ.get("TEMPLATE_MESSAGE", ""),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
    }


def _overall_status(inputs: dict[str, str]) -> tuple[str, list[str], list[str]]:
    status = "PASS"
    blocking: list[str] = []
    warnings: list[str] = []
    bypass_used = inputs["bypass_used"].casefold() == "true"
    if inputs["description"] == "FAIL":
        status = "FAIL"
        blocking.append("PR description does not match actual changes")
    elif inputs["description"] == "ERROR":
        status = "ERROR"
        blocking.append("Description validation error")
    elif bypass_used:
        status = "BYPASSED"
        warnings.append(
            "Description validation BYPASSED via "
            f"'{inputs['bypass_label']}' label "
            f"({inputs['bypass_count']} CRITICAL files suppressed). "
            "See job summary for details."
        )
    if inputs["keywords"] == "WARN":
        warnings.append("No GitHub issue linking keywords found (Closes, Fixes, Resolves #N)")
    if inputs["template"] == "WARN" and inputs["template_message"]:
        warnings.append(inputs["template_message"])
    return status, blocking, warnings


def _alert_type(overall_status: str, warnings: list[str]) -> str:
    if overall_status == "FAIL":
        return "CAUTION"
    if overall_status in {"ERROR", "BYPASSED"}:
        return "WARNING"
    if warnings:
        return "NOTE"
    return "TIP"


def _description_status(inputs: dict[str, str]) -> str:
    if inputs["bypass_used"].casefold() == "true" and inputs["description"] != "ERROR":
        return "BYPASSED (label override)"
    return inputs["description"]


def build_report(inputs: dict[str, str]) -> tuple[str, str]:
    overall_status, blocking, warnings = _overall_status(inputs)
    emoji = "✅" if overall_status == "PASS" else "⚠️" if overall_status == "BYPASSED" else "❌"
    lines = [
        "<!-- PR-VALIDATION -->",
        "",
        "## PR Validation Report",
        "",
        f"> [!{_alert_type(overall_status, warnings)}]",
        f"> {emoji} **Status: {overall_status}**",
        "",
        "### Description Validation",
        "",
        "| Check | Status |",
        "|:------|:-------|",
        f"| Description matches diff | {_description_status(inputs)} |",
        "",
        "### PR Standards",
        "",
        "| Check | Status |",
        "|:------|:-------|",
        f"| Issue linking keywords | {inputs['keywords']} |",
        f"| Template compliance | {inputs['template']} |",
    ]
    if blocking:
        lines.extend(["", "### ⚠️ Blocking Issues", ""])
        lines.extend(f"- {issue}" for issue in blocking)
    if warnings:
        lines.extend(["", "### ⚡ Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "---",
            "",
            (
                "<sub>Powered by [PR Validation]"
                f"(https://github.com/{inputs['repository']}) workflow</sub>"
            ),
        ]
    )
    return overall_status, "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    # Resolve required config before creating any file. Writing the report
    # first left an artifact on disk for a step that was about to fail.
    output_path = _resolve_output_path()
    if output_path is None:
        return CONFIG_ERROR
    status, report = build_report(_status_inputs())
    REPORT_PATH.write_text(report, encoding="utf-8")
    _append_output(output_path, "overall_status", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
