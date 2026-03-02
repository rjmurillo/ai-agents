#!/usr/bin/env python3
"""Validate QA agent output completeness when qa subagent stops.

Claude Code SubagentStop hook that verifies QA validation reports are
complete and contain required sections. Ensures quality gates are
properly executed per SESSION-PROTOCOL requirements.

Hook Type: SubagentStop
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)

Related:
    .agents/SESSION-PROTOCOL.md
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
"""

import json
import os
import re
import sys


# Required section header patterns (markdown h1-h3)
QA_SECTION_PATTERNS = {
    "Test Strategy/Testing Approach/Test Plan (as section header)": (
        r"(?m)^#{1,3}\s*(Test Strategy|Testing Approach|Test Plan)\s*$"
    ),
    "Test Results/Validation Results/Test Execution (as section header)": (
        r"(?m)^#{1,3}\s*(Test Results|Validation Results|Test Execution)\s*$"
    ),
    "Coverage/Test Coverage/Acceptance Criteria (as section header)": (
        r"(?m)^#{1,3}\s*(Coverage|Test Coverage|Acceptance Criteria)\s*$"
    ),
}


def is_qa_agent(hook_input: dict) -> bool:
    """Check if the subagent is a QA agent."""
    return hook_input.get("subagent_type") == "qa"


def get_transcript_path(hook_input: dict) -> str | None:
    """Extract and validate transcript path from hook input."""
    path = hook_input.get("transcript_path", "")
    if not path or not path.strip():
        return None
    path = path.strip()
    if os.path.isfile(path):
        return path
    return None


def get_missing_qa_sections(transcript: str) -> list[str]:
    """Return list of missing QA section names."""
    missing = []
    for section_name, pattern in QA_SECTION_PATTERNS.items():
        if not re.search(pattern, transcript):
            missing.append(section_name)
    return missing


def log_transcript_issue(hook_input: dict) -> None:
    """Log why transcript path is null for troubleshooting."""
    if "transcript_path" not in hook_input:
        print(
            "QA validator: No transcript_path property in hook input. "
            "Agent may not have provided transcript. Validation skipped.",
            file=sys.stderr,
        )
    elif not hook_input.get("transcript_path", "").strip():
        print(
            "QA validator: transcript_path property exists but is "
            "empty/whitespace. Validation skipped.",
            file=sys.stderr,
        )
    else:
        print(
            f"QA validator: Transcript file does not exist at "
            f"'{hook_input['transcript_path']}'. Agent may have failed "
            f"or transcript not written. Validation skipped.",
            file=sys.stderr,
        )


def main() -> None:
    """Entry point for the QA agent validator hook."""
    try:
        if sys.stdin.isatty():
            sys.exit(0)

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            sys.exit(0)

        hook_input = json.loads(input_text)

        if not is_qa_agent(hook_input):
            sys.exit(0)

        transcript_path = get_transcript_path(hook_input)
        if transcript_path is None:
            log_transcript_issue(hook_input)
            sys.exit(0)

        with open(transcript_path, encoding="utf-8") as f:
            transcript = f.read()

        missing_sections = get_missing_qa_sections(transcript)

        if missing_sections:
            missing_list = ", ".join(missing_sections)
            print(
                f"\n**QA VALIDATION FAILURE**: QA agent report is incomplete "
                f"and does NOT meet SESSION-PROTOCOL requirements.\n\n"
                f"Missing required sections: {missing_list}\n\n"
                f"ACTION REQUIRED: Re-run QA agent with complete report "
                f"including all required sections per "
                f".agents/SESSION-PROTOCOL.md\n"
            )
            print(
                f"QA validation failed: Missing sections - {missing_list}",
                file=sys.stderr,
            )
        else:
            print(
                "\n**QA Validation PASSED**: All required sections present "
                "in QA report.\n"
            )

        # Machine-readable validation result
        validation_result = json.dumps({
            "validation_passed": len(missing_sections) == 0,
            "missing_sections": missing_sections,
            "transcript_path": transcript_path,
        })
        print(validation_result)

        sys.exit(0)

    except (OSError, PermissionError) as exc:
        print(
            f"QA validator file error: Cannot read transcript - {exc}",
            file=sys.stderr,
        )
        print(
            "\n**QA Validation ERROR**: Cannot access QA agent transcript "
            "file. Validation skipped.\n"
        )
        sys.exit(0)

    except Exception as exc:
        print(
            f"QA validator unexpected error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        print(
            f"\n**QA Validation ERROR**: Unexpected error during validation. "
            f"MUST investigate: {exc}\n"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
