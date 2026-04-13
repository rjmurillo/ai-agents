"""Canonical: scripts/github_core/output.py. Sync via scripts/sync_plugin_lib.py.

Provides write_skill_output, write_skill_error, and get_output_format
functions for consistent skill script output formatting. All skill scripts
should use these helpers to produce either JSON or human-readable output.

Related: ADR-056 (Skill Output Format Standardization)
Related: ADR-035 (Exit Code Standardization)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime


def add_output_format_arg(parser: argparse.ArgumentParser) -> None:
    """Add the standard --output-format argument to an argparse parser.

    Args:
        parser: The ArgumentParser to add the argument to.
    """
    parser.add_argument(
        "--output-format",
        choices=["json", "human", "auto"],
        default="auto",
        help=(
            "Output format. 'json' emits only JSON on stdout. "
            "'human' emits colored text summaries. "
            "'auto' detects context (default: auto)."
        ),
    )


def get_output_format(requested: str = "auto") -> str:
    """Resolve the output format based on requested value and execution context.

    Args:
        requested: The requested format: json, human, or auto.

    Returns:
        Either 'json' or 'human'.
    """
    requested_lower = requested.lower()
    if requested_lower in ("json", "human"):
        return requested_lower

    # CI environments always get JSON
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("TF_BUILD"):
        return "json"

    # Check if stdout is redirected (not a TTY)
    if not sys.stdout.isatty():
        return "json"

    return "human"


def write_skill_output(
    data: object,
    *,
    output_format: str = "auto",
    human_summary: str = "",
    status: str = "PASS",
    script_name: str = "",
    version: str = "1.0.0",
) -> str | None:
    """Emit a standardized skill output envelope.

    Args:
        data: The operation-specific result data.
        output_format: Output format: json, human, or auto.
        human_summary: One-line summary for human-readable output.
        status: Status indicator: PASS, FAIL, WARNING, INFO.
        script_name: Name of the calling script (auto-detected if omitted).
        version: Script version string.

    Returns:
        JSON string when format is json, None when human.
    """
    resolved = get_output_format(output_format)

    if not script_name:
        script_name = _detect_script_name()

    envelope = {
        "Success": True,
        "Data": data,
        "Error": None,
        "Metadata": {
            "Script": script_name,
            "Version": version,
            "Timestamp": datetime.now(UTC).isoformat(),
        },
    }

    if resolved == "json":
        output = json.dumps(envelope, separators=(",", ":"))
        print(output)
        return output

    message = human_summary or "Operation completed"
    color = _status_color(status)
    print(f"{color}[{status}] {message}\033[0m")
    return None


def write_skill_error(
    message: str,
    exit_code: int,
    *,
    error_type: str = "General",
    output_format: str = "auto",
    script_name: str = "",
    version: str = "1.0.0",
    extra: dict[str, object] | None = None,
) -> str | None:
    """Emit a standardized skill error envelope.

    Args:
        message: Human-readable error message.
        exit_code: Exit code per ADR-035.
        error_type: Machine-readable error category.
        output_format: Output format: json, human, or auto.
        script_name: Name of the calling script.
        version: Script version string.
        extra: Additional properties to merge into the Data field.

    Returns:
        JSON string when format is json, None when human.
    """
    valid_types = ("NotFound", "ApiError", "AuthError", "InvalidParams", "Timeout", "General")
    if error_type not in valid_types:
        raise ValueError(f"error_type must be one of {valid_types}, got: {error_type}")

    resolved = get_output_format(output_format)

    if not script_name:
        script_name = _detect_script_name()

    envelope = {
        "Success": False,
        "Data": extra,
        "Error": {
            "Message": message,
            "Code": exit_code,
            "Type": error_type,
        },
        "Metadata": {
            "Script": script_name,
            "Version": version,
            "Timestamp": datetime.now(UTC).isoformat(),
        },
    }

    if resolved == "json":
        output = json.dumps(envelope, separators=(",", ":"))
        print(output)
        return output

    print(f"\033[31m[FAIL] {message}\033[0m")
    return None


def _detect_script_name() -> str:
    """Detect the calling script name from the call stack."""
    import inspect

    frame = inspect.currentframe()
    if frame and frame.f_back and frame.f_back.f_back:
        caller_file = frame.f_back.f_back.f_globals.get("__file__", "")
        if caller_file and isinstance(caller_file, str):
            return os.path.basename(caller_file)
    return "unknown"


def _status_color(status: str) -> str:
    """Return ANSI color code for the given status."""
    colors = {
        "PASS": "\033[32m",
        "FAIL": "\033[31m",
        "WARNING": "\033[33m",
        "INFO": "\033[36m",
    }
    return colors.get(status, "")
