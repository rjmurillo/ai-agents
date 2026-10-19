#!/usr/bin/env python3
"""Build the PR validation report and write workflow outputs."""

from __future__ import annotations

import os
import re
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
        "finding": os.environ.get("DESCRIPTION_FINDING", ""),
        "bypass_used": os.environ.get("BYPASS_USED", ""),
        "bypass_label": os.environ.get("BYPASS_LABEL", ""),
        "bypass_count": os.environ.get("BYPASS_COUNT", ""),
        "keywords": os.environ.get("KEYWORDS_STATUS", ""),
        "template": os.environ.get("TEMPLATE_STATUS", ""),
        "template_message": os.environ.get("TEMPLATE_MESSAGE", ""),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
    }


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
# A backtick would end the code span the finding sits in. Angle brackets would
# open HTML or a comment if the span ever broke.
_BREAKOUT_CHARS = re.compile(r"[`<>]")
# `@name` at the start of a word notifies a user or team. An address such as
# `a@b.example` has a word character before the `@` and is left alone.
_MENTION = re.compile(r"(?<!\w)@(?=[\w-])")


def _neutralize(finding: str) -> str:
    """Return ``finding`` as one inert line for the bot comment.

    The producer (``map_pr_description_result._clean``) already cleans the value,
    but this report is the last step before the text is published, so it does
    not rely on that. Control characters and newlines collapse to single spaces.
    Backticks and angle brackets are removed, and ``@`` is dropped from a mention.
    Other punctuation stays: inside the code span it is inert, and removing it
    would rewrite file names such as ``pages/[id].tsx``.
    """
    stripped = _BREAKOUT_CHARS.sub("", _CONTROL_CHARS.sub(" ", finding))
    return _MENTION.sub("", " ".join(stripped.split()))


def _with_finding(message: str, finding: str) -> str:
    """Name the first failing finding so the failed step is actionable."""
    clean = _neutralize(finding)
    return f"{message}: `{clean}`" if clean else message


def _overall_status(inputs: dict[str, str]) -> tuple[str, list[str], list[str]]:
    status = "PASS"
    blocking: list[str] = []
    warnings: list[str] = []
    bypass_used = inputs["bypass_used"].casefold() == "true"
    if inputs["description"] == "FAIL":
        status = "FAIL"
        blocking.append(
            _with_finding("PR description does not match actual changes", inputs["finding"])
        )
    elif inputs["description"] == "ERROR":
        status = "ERROR"
        blocking.append(_with_finding("Description validation error", inputs["finding"]))
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


def blocking_summary(inputs: dict[str, str]) -> str:
    """One line naming each blocking issue, for the enforce step's error."""
    return " ".join("; ".join(_overall_status(inputs)[1]).split())


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    # Resolve required config before creating any file. Writing the report
    # first left an artifact on disk for a step that was about to fail.
    output_path = _resolve_output_path()
    if output_path is None:
        return CONFIG_ERROR
    inputs = _status_inputs()
    status, report = build_report(inputs)
    REPORT_PATH.write_text(report, encoding="utf-8")
    _append_output(output_path, "overall_status", status)
    _append_output(output_path, "blocking_summary", blocking_summary(inputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
