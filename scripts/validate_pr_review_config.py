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

COMPLETION_CRITERIA_FIELDS = ["criterion", "verification", "required"]
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

    if "completion_criteria" in config:
        for i, item in enumerate(config["completion_criteria"]):
            for field in COMPLETION_CRITERIA_FIELDS:
                if field not in item:
                    errors.append(
                        f"completion_criteria[{i}] missing field: {field}"
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

    return errors


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

    config_path = Path(args.config_path)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 2

    if yaml is None:
        print(
            "WARNING: PyYAML not installed. Skipping deep validation.",
            file=sys.stderr,
        )
        print(f"Config file exists: {config_path}")
        return 0

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
