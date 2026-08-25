"""Standard skill output helpers per ADR-056.

Provides write_skill_output, write_skill_error, and get_output_format
functions for consistent skill script output formatting. All skill scripts
should use these helpers to produce either JSON or human-readable output.

Related: ADR-056 (Skill Output Format Standardization)
Related: ADR-103 (Python contract correction; Error.Type is required)
Related: ADR-035 (Exit Code Standardization)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

# The set of Error.Type values write_skill_error accepts. Module-level so it
# is a single, importable source of truth: tests/test_skill_output.py derives
# its parametrize list from this constant (rather than a second hardcoded
# copy) and separately asserts it matches VALID_ERROR_TYPES in
# scripts/validate_skill_output.py and the enum in
# .agents/schemas/skill-output.schema.json, so THOSE THREE contract copies
# cannot drift unnoticed (ADR-103). This is not repo-wide: at least one more
# independently-maintained ErrorType Literal exists at
# .claude/skills/orphan-ref-validator/scripts/envelope.py:133
# (render_error_envelope), carrying a 6-of-8 subset (missing
# RateLimitError, VerificationFailed). An earlier version of this comment
# called that copy "fail-closed", which is wrong: `typing.Literal` is a
# static annotation only, `render_error_envelope` performs no runtime
# membership check on `error_type`, and Python does not enforce Literal at
# all at runtime, so a caller bypassing the type checker (or one whose
# checker silently disagrees) can still construct an envelope with a
# `Type` value outside the 6-value subset. This is an unguarded fourth
# producer, not evidence that no correctness gap exists there; pre-existing
# and out of this round's scope, flagged as a follow-up rather than fixed
# here (Copilot review on PR #5283, correcting the ADR-103 Round 5
# convergence check's high-level-advisor seat, which made the same
# mistaken claim).
VALID_ERROR_TYPES = (
    "NotFound",
    "ApiError",
    "AuthError",
    "InvalidParams",
    "RateLimitError",
    "Timeout",
    "General",
    "VerificationFailed",
)


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
    if error_type not in VALID_ERROR_TYPES:
        raise ValueError(
            f"error_type must be one of {VALID_ERROR_TYPES}, got: {error_type}"
        )
    if not message:
        # skill-output.schema.json requires Error.Message "minLength": 1
        # (ADR-103 Round 5). Before this guard, the schema and validator
        # both rejected an empty Message while nothing on the producer
        # side prevented constructing one: an errored call with a bare
        # `Exception()` (no args) yields `str(exc) == ""`. This guard
        # closes that gap for real, instead of leaving it as a
        # documented, unenforced risk (adr-review critic seat, ADR-103
        # Round 5 convergence check). Several callers in this repo
        # already pass `str(exc)` or a dict-sourced message (for example
        # `.claude/skills/github/scripts/pr/edit_pr_body.py`,
        # `check_data["Message"]` in `get_pr_checks.py`), none of which
        # is guaranteed non-empty by construction; an earlier version of
        # this comment incorrectly claimed every other caller passes a
        # literal string. Callers whose upstream exception could
        # stringify empty (a subprocess exiting non-zero with blank
        # stderr, for example) MUST guarantee a non-empty message before
        # this call, typically with `str(exc) or "<fallback>"` at the
        # `raise` site (adr-review independent-thinker seat, same
        # convergence round, which found two `raise RuntimeError(...)`
        # sites in `edit_pr_body.py` that did not).
        raise ValueError("message must be non-empty")
    if not isinstance(message, str):
        # `if not message:` above is a truthiness check, not a type
        # check: a truthy non-string value (`123`, `["a"]`, an
        # exception object passed by mistake instead of `str(exc)`)
        # passes it and still reaches `json.dumps`, producing
        # `Error.Message: 123` or similar, which both the schema
        # ("type": "string") and validate_envelope reject. The producer
        # must not be able to construct an envelope its own validators
        # reject; adding this alongside the emptiness guard closes that
        # gap the same way the emptiness guard closed the empty-string
        # one (Copilot review on PR #5283, following the ADR-103 Round 5
        # convergence check).
        raise ValueError(f"message must be a string, got: {type(message).__name__}")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        # skill-output.schema.json types Error.Code as "type": "integer"
        # (pre-dates ADR-103) and both scripts/validate_skill_output.py
        # and mypy's static check on this file's `exit_code: int`
        # parameter already treat a non-int value as wrong. Neither
        # catches `exit_code=True` at the caller: Python's `bool`
        # subclasses `int`, `isinstance(True, int)` is `True`, and mypy
        # accepts a `bool` argument for an `int`-typed parameter (a
        # `bool` is-a `int` under PEP 484's nominal subtyping), so a
        # type-correct call could still construct `Error.Code: true`,
        # which the schema and validator both reject. Same class of
        # producer/schema disagreement as the `message` guard above,
        # found while re-checking for other instances (adr-review
        # independent-thinker seat, ADR-103 Round 5 convergence check,
        # finding F1).
        raise ValueError(f"exit_code must be an integer, got: {type(exit_code).__name__}")

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
        caller_file: object = frame.f_back.f_back.f_globals.get("__file__")
        if isinstance(caller_file, str) and caller_file:
            script_path: str = caller_file
            return os.path.basename(script_path)
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
