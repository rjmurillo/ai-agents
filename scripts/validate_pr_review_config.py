#!/usr/bin/env python3
"""Validate pr-review-config.yaml against expected schema.

Ensures all required sections and fields are present in the
pr-review configuration file.

EXIT CODES:
  0  - Success: Config is valid
  1  - Error: Schema violations detected
  2  - Error: Config file not found or parse failure

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402

try:
    import yaml
except ImportError:
    # Fall back to a simple check if PyYAML is not available
    yaml = None  # type: ignore[assignment]

REQUIRED_TOP_LEVEL_KEYS = [
    "scripts",
    "check_failure_actions",
    "error_recovery",
    "completion_criteria",
    "failure_handling",
    "worktree_constraints",
    "related_memories",
    "thread_resolution",
    "invocation_limits",
    "output_constraints",
]

INVOCATION_LIMIT_FIELDS = [
    "all_open_max_prs",
    "all_open_overflow_action",
    "completion_gate_max_retries",
    "completion_gate_overflow_action",
]

OUTPUT_CONSTRAINT_FIELDS = [
    "per_pr_max_response_tokens",
    "summary_format",
    "summary_format_allowed_values",
    "summary_required_columns",
]

REQUIRED_SCRIPT_KEYS = [
    "get_pr_context",
    "test_pr_merged",
    "get_review_threads",
    "get_unresolved_threads",
    "get_unaddressed_comments",
    "get_pr_checks",
    "add_thread_reply",
    "resolve_thread",
]

# Keys only required for claude_code section (has --resolve flag variant)
CLAUDE_CODE_ONLY_KEYS = [
    "add_thread_reply_resolve",
]

REQUIRED_SCRIPT_SECTIONS = ["claude_code", "copilot"]

# Each completion criterion is a dispatchable verification: a command whose
# stdout JSON drives a pass_when expression. The agent no longer narrates
# verdicts; the command output IS the verdict. See pr-review-config.yaml
# header comments for the pass_when DSL.
COMPLETION_CRITERIA_REQUIRED_FIELDS = ["name", "verification", "command"]
COMPLETION_CRITERIA_PASS_FIELDS = ["pass_when", "pass_when_python"]
ERROR_RECOVERY_FIELDS = ["scenario", "action"]
CHECK_FAILURE_FIELDS = ["check_type", "action"]
FAILURE_HANDLING_FIELDS = ["type", "action"]
RELATED_MEMORY_FIELDS = ["name", "purpose"]


def validate_config(config: dict) -> list[str]:
    """Return list of validation errors. Empty list means valid."""
    errors: list[str] = []

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in config:
            errors.append(f"Missing required top-level key: {key}")

    if "scripts" in config:
        scripts = config["scripts"]
        for section in REQUIRED_SCRIPT_SECTIONS:
            if section not in scripts:
                errors.append(f"Missing scripts section: {section}")
                continue
            for script_key in REQUIRED_SCRIPT_KEYS:
                if script_key not in scripts[section]:
                    errors.append(
                        f"Missing script in scripts.{section}: {script_key}"
                    )
            # Check claude_code-specific keys
            if section == "claude_code":
                for script_key in CLAUDE_CODE_ONLY_KEYS:
                    if script_key not in scripts[section]:
                        errors.append(
                            f"Missing script in scripts.{section}: {script_key}"
                        )

    completion_criteria = config.get("completion_criteria")
    if completion_criteria is not None and not isinstance(
        completion_criteria, list,
    ):
        # Per Copilot review: if YAML parses ``completion_criteria`` as
        # a mapping or string, the per-element loop would iterate
        # keys/chars and emit a noisy series of "must be a mapping"
        # errors. Reject the container shape with a single clear
        # message and skip per-criterion validation. Other sections of
        # the config still get validated below. Mirrors the
        # dispatcher's behavior.
        errors.append(
            f"completion_criteria must be a list "
            f"(got {type(completion_criteria).__name__})"
        )
    elif "completion_criteria" in config:
        for i, item in enumerate(config["completion_criteria"]):
            if not isinstance(item, dict):
                errors.append(
                    f"completion_criteria[{i}] must be a mapping"
                )
                continue
            for field in COMPLETION_CRITERIA_REQUIRED_FIELDS:
                if field not in item:
                    errors.append(
                        f"completion_criteria[{i}] missing field: {field}"
                    )
            # Exactly one of pass_when / pass_when_python must be set.
            # Both-set is ambiguous because the dispatcher silently picks
            # pass_when_python first; reject it at validation time so
            # the ambiguity never reaches runtime.
            # Check both key presence AND truthiness: a key with null or ""
            # passes `f in item` but fails the dispatcher's `if not pass_when`
            # check at runtime. Matching truthiness here ensures the validator
            # rejects configs that would fail at dispatch time.
            present = [
                f for f in COMPLETION_CRITERIA_PASS_FIELDS if item.get(f)
            ]
            if not present:
                errors.append(
                    f"completion_criteria[{i}] missing field: pass_when "
                    f"(or pass_when_python)"
                )
            elif len(present) > 1:
                errors.append(
                    f"completion_criteria[{i}] has both pass_when and "
                    f"pass_when_python; specify exactly one"
                )
            verification = item.get("verification")
            if verification is not None and verification != "command":
                errors.append(
                    f"completion_criteria[{i}].verification must be "
                    f"'command' (got {verification!r})"
                )
            fail_open = item.get("fail_open")
            if fail_open is not None and not isinstance(fail_open, bool):
                errors.append(
                    f"completion_criteria[{i}].fail_open must be a boolean"
                )
            # Per Copilot review: presence is not enough; reject empty
            # or wrong-typed values that would slip past the dispatcher
            # only to crash later.
            if "name" in item and (
                not isinstance(item["name"], str) or not item["name"].strip()
            ):
                errors.append(
                    f"completion_criteria[{i}].name must be a non-empty string"
                )
            if "command" in item and (
                not isinstance(item["command"], str)
                or not item["command"].strip()
            ):
                errors.append(
                    f"completion_criteria[{i}].command must be a non-empty string"
                )
            for field in ("pass_when", "pass_when_python"):
                if field in item and (
                    not isinstance(item[field], str)
                    or not item[field].strip()
                ):
                    errors.append(
                        f"completion_criteria[{i}].{field} must be a "
                        f"non-empty string"
                    )

    if "error_recovery" in config:
        for i, item in enumerate(config["error_recovery"]):
            for field in ERROR_RECOVERY_FIELDS:
                if field not in item:
                    errors.append(f"error_recovery[{i}] missing field: {field}")

    if "check_failure_actions" in config:
        for i, item in enumerate(config["check_failure_actions"]):
            for field in CHECK_FAILURE_FIELDS:
                if field not in item:
                    errors.append(
                        f"check_failure_actions[{i}] missing field: {field}"
                    )

    if "failure_handling" in config:
        for i, item in enumerate(config["failure_handling"]):
            for field in FAILURE_HANDLING_FIELDS:
                if field not in item:
                    errors.append(
                        f"failure_handling[{i}] missing field: {field}"
                    )

    if "related_memories" in config:
        for i, item in enumerate(config["related_memories"]):
            for field in RELATED_MEMORY_FIELDS:
                if field not in item:
                    errors.append(
                        f"related_memories[{i}] missing field: {field}"
                    )

    if "worktree_constraints" in config:
        if not isinstance(config["worktree_constraints"], list):
            errors.append("worktree_constraints must be a list")
        elif len(config["worktree_constraints"]) == 0:
            errors.append("worktree_constraints must not be empty")

    if "thread_resolution" in config:
        tr = config["thread_resolution"]
        if "note" not in tr:
            errors.append("thread_resolution missing field: note")
        if "batch_graphql_template" not in tr:
            errors.append(
                "thread_resolution missing field: batch_graphql_template"
            )

    if "invocation_limits" in config:
        _validate_invocation_limits(config["invocation_limits"], errors)

    if "output_constraints" in config:
        _validate_output_constraints(config["output_constraints"], errors)

    return errors


def _validate_invocation_limits(il: object, errors: list[str]) -> None:
    """Validate invocation_limits section.

    Guards against non-mapping values (e.g., null) and checks types and
    ranges per CodeRabbit feedback on PR #1671.
    """
    if not isinstance(il, dict):
        errors.append("invocation_limits must be a mapping")
        return

    for field in INVOCATION_LIMIT_FIELDS:
        if field not in il:
            errors.append(f"invocation_limits missing field: {field}")

    max_prs = il.get("all_open_max_prs")
    if max_prs is not None and (not isinstance(max_prs, int) or isinstance(max_prs, bool) or max_prs < 1):
        errors.append(
            "invocation_limits.all_open_max_prs must be an integer >= 1"
        )

    retries = il.get("completion_gate_max_retries")
    if retries is not None and (not isinstance(retries, int) or isinstance(retries, bool) or retries < 0):
        errors.append(
            "invocation_limits.completion_gate_max_retries must be an integer >= 0"
        )

    for field in ("all_open_overflow_action", "completion_gate_overflow_action"):
        value = il.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(
                f"invocation_limits.{field} must be a non-empty string"
            )


def _validate_output_constraints(oc: object, errors: list[str]) -> None:
    """Validate output_constraints section.

    Guards against non-mapping values (e.g., null) and checks types and
    ranges per CodeRabbit feedback on PR #1671.
    """
    if not isinstance(oc, dict):
        errors.append("output_constraints must be a mapping")
        return

    for field in OUTPUT_CONSTRAINT_FIELDS:
        if field not in oc:
            errors.append(f"output_constraints missing field: {field}")

    max_tokens = oc.get("per_pr_max_response_tokens")
    if max_tokens is not None and (
        not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1
    ):
        errors.append(
            "output_constraints.per_pr_max_response_tokens must be an integer >= 1"
        )

    summary_format = oc.get("summary_format")
    if summary_format is not None and (
        not isinstance(summary_format, str) or not summary_format.strip()
    ):
        errors.append(
            "output_constraints.summary_format must be a non-empty string"
        )

    allowed = oc.get("summary_format_allowed_values")
    if allowed is not None and (
        not isinstance(allowed, list)
        or len(allowed) == 0
        or any(not isinstance(v, str) or not v.strip() for v in allowed)
    ):
        errors.append(
            "output_constraints.summary_format_allowed_values must be a non-empty list of non-empty strings"
        )

    if (
        isinstance(summary_format, str)
        and isinstance(allowed, list)
        and all(isinstance(v, str) for v in allowed)
        and summary_format not in allowed
    ):
        errors.append(
            "output_constraints.summary_format must be one of summary_format_allowed_values"
        )

    cols = oc.get("summary_required_columns")
    if (
        not isinstance(cols, list)
        or len(cols) == 0
        or any(not isinstance(c, str) or not c.strip() for c in cols)
    ):
        errors.append(
            "output_constraints.summary_required_columns must be a non-empty list of non-empty strings"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate pr-review-config.yaml schema"
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        default=".claude/commands/pr-review-config.yaml",
        help="Path to config file (default: .claude/commands/pr-review-config.yaml)",
    )
    args = parser.parse_args()

    # CWE-22: Validate path stays within project root before opening.
    try:
        config_path = validate_safe_path(args.config_path, _PROJECT_ROOT)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: Invalid config path: {e}", file=sys.stderr)
        return 2

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 2

    if yaml is None:
        print(
            "ERROR: PyYAML not installed. Cannot validate config schema.",
            file=sys.stderr,
        )
        return 2

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse YAML: {e}", file=sys.stderr)
        return 2

    if not isinstance(config, dict):
        print("ERROR: Config must be a YAML mapping", file=sys.stderr)
        return 2

    errors = validate_config(config)

    if errors:
        print(f"FAIL: {len(errors)} validation error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"OK: {config_path} is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
