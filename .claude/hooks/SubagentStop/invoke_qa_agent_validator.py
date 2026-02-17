#!/usr/bin/env python3
"""Validate QA agent output completeness when qa subagent stops.

Claude Code SubagentStop hook that verifies QA validation reports are
complete and contain required sections. This ensures quality gates are
properly executed per SESSION-PROTOCOL requirements.

Part of the hooks expansion implementation (Issue #773, Phase 2).

Hook Type: SubagentStop
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Section header patterns for QA reports (markdown h1-h3)
TEST_STRATEGY_PATTERN = re.compile(r"(?m)^#{1,3}\s*(Test Strategy|Testing Approach|Test Plan)\s*$")
TEST_RESULTS_PATTERN = re.compile(
    r"(?m)^#{1,3}\s*(Test Results|Validation Results|Test Execution)\s*$"
)
COVERAGE_PATTERN = re.compile(r"(?m)^#{1,3}\s*(Coverage|Test Coverage|Acceptance Criteria)\s*$")


def is_qa_agent(hook_input: dict[str, object]) -> bool:
    """Check if the subagent is a QA agent."""
    return hook_input.get("subagent_type") == "qa"


def get_transcript_path(hook_input: dict[str, object]) -> str | None:
    """Extract and validate transcript path from hook input."""
    path = hook_input.get("transcript_path")
    if not isinstance(path, str) or not path.strip():
        return None
    if not Path(path).exists():
        return None
    return path


def get_missing_qa_sections(transcript: str) -> list[str]:
    """Check for missing required QA report sections."""
    missing: list[str] = []

    if not TEST_STRATEGY_PATTERN.search(transcript):
        missing.append("Test Strategy/Testing Approach/Test Plan (as section header)")
    if not TEST_RESULTS_PATTERN.search(transcript):
        missing.append("Test Results/Validation Results/Test Execution (as section header)")
    if not COVERAGE_PATTERN.search(transcript):
        missing.append("Coverage/Test Coverage/Acceptance Criteria (as section header)")

    return missing


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        if not is_qa_agent(hook_input):
            return 0

        transcript_path = get_transcript_path(hook_input)
        if transcript_path is None:
            # Log why transcript is missing for troubleshooting
            if "transcript_path" not in hook_input:
                print(
                    "QA validator: No transcript_path property in hook input. "
                    "Agent may not have provided transcript. Validation skipped.",
                    file=sys.stderr,
                )
            elif not hook_input.get("transcript_path", "").strip():
                print(
                    "QA validator: transcript_path property exists but is empty/whitespace. "
                    "Validation skipped.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"QA validator: Transcript file does not exist at "
                    f"'{hook_input['transcript_path']}'. "
                    f"Agent may have failed or transcript not written. Validation skipped.",
                    file=sys.stderr,
                )
            return 0

        transcript = Path(transcript_path).read_text(encoding="utf-8")
        missing_sections = get_missing_qa_sections(transcript)

        if missing_sections:
            missing_list = ", ".join(missing_sections)
            protocol_ref = ""
            protocol_path = Path(hook_input.get("cwd", ".")) / ".agents" / "SESSION-PROTOCOL.md"
            if protocol_path.is_file():
                protocol_ref = " per .agents/SESSION-PROTOCOL.md"
            print(
                f"\n**QA VALIDATION FAILURE**: QA agent report is incomplete "
                f"and does NOT meet SESSION-PROTOCOL requirements.\n\n"
                f"Missing required sections: {missing_list}\n\n"
                f"ACTION REQUIRED: Re-run QA agent with complete report "
                f"including all required sections{protocol_ref}\n"
            )
            print(f"QA validation failed: Missing sections - {missing_list}", file=sys.stderr)
        else:
            print("\n**QA Validation PASSED**: All required sections present in QA report.\n")

        validation_result = {
            "validation_passed": len(missing_sections) == 0,
            "missing_sections": missing_sections,
            "transcript_path": transcript_path,
        }
        print(json.dumps(validation_result))

        return 0

    except (OSError, PermissionError) as exc:
        print(f"QA validator file error: Cannot read transcript - {exc}", file=sys.stderr)
        print(
            "\n**QA Validation ERROR**: Cannot access QA agent transcript file. "
            "Validation skipped.\n"
        )
        return 0

    except Exception as exc:
        print(
            f"QA validator unexpected error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        print(
            f"\n**QA Validation ERROR**: Unexpected error during validation. "
            f"MUST investigate: {exc}\n"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
