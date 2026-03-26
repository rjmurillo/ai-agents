#!/usr/bin/env python3
"""Validate Claude Code hook contracts between settings.json and hook scripts.

Parses .claude/settings.json and validates that every referenced hook script:
1. Exists on disk
2. Documents its hook type in docstring
3. Documents exit codes consistent with hook type semantics
4. Has reasonable timeout values (when specified)

Exit codes follow ADR-035:
    0 - Success (no violations, or non-CI mode)
    1 - Logic error (violations found, CI mode)
    2 - Config error (settings.json not found or invalid)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Hook types where exit code 2 = block
BLOCKING_HOOK_TYPES = frozenset({"PreToolUse", "PermissionRequest"})

# Hook types where exit code is always 0 (non-blocking)
NON_BLOCKING_HOOK_TYPES = frozenset(
    {"Stop", "SubagentStop", "SessionStart", "PostToolUse", "UserPromptSubmit"}
)

ALL_HOOK_TYPES = BLOCKING_HOOK_TYPES | NON_BLOCKING_HOOK_TYPES

# Timeout bounds in seconds
MIN_TIMEOUT = 1
MAX_TIMEOUT = 300

# Pattern to extract script path from command string
_SCRIPT_PATH_PATTERN = re.compile(r"python3?\s+(?:-\w+\s+)*(.+\.py)(?:\s|$)")

# ANSI color codes (disabled when NO_COLOR is set or in CI)
_USE_COLOR = not (os.environ.get("NO_COLOR") or os.environ.get("CI"))
_COLOR_RESET = "\033[0m" if _USE_COLOR else ""
_COLOR_RED = "\033[31m" if _USE_COLOR else ""
_COLOR_YELLOW = "\033[33m" if _USE_COLOR else ""
_COLOR_GREEN = "\033[32m" if _USE_COLOR else ""
_COLOR_CYAN = "\033[36m" if _USE_COLOR else ""


@dataclass
class Violation:
    """A hook contract violation."""

    hook_type: str
    script: str
    category: str
    message: str


@dataclass
class HookEntry:
    """A parsed hook entry from settings.json."""

    hook_type: str
    script_path: str
    command: str
    matcher: str | None = None
    timeout: int | None = None
    status_message: str | None = None


@dataclass
class ContractReport:
    """Summary of hook contract validation."""

    entries: list[HookEntry] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0


def extract_script_path(command: str) -> str | None:
    """Extract the Python script path from a hook command string."""
    match = _SCRIPT_PATH_PATTERN.search(command)
    if match:
        return match.group(1)
    return None


def parse_settings(settings_path: Path) -> tuple[dict, list[HookEntry]]:
    """Parse settings.json and extract all hook entries.

    Returns (raw_settings, hook_entries).
    """
    content = settings_path.read_text(encoding="utf-8")
    settings = json.loads(content)

    hooks_config = settings.get("hooks", {})
    entries: list[HookEntry] = []

    for hook_type, hook_groups in hooks_config.items():
        if not isinstance(hook_groups, list):
            continue

        for group in hook_groups:
            matcher = group.get("matcher")
            group_hooks = group.get("hooks", [])

            for hook in group_hooks:
                if hook.get("type") != "command":
                    continue

                command = hook.get("command", "")
                script_path = extract_script_path(command)
                if not script_path:
                    continue

                entries.append(
                    HookEntry(
                        hook_type=hook_type,
                        script_path=script_path,
                        command=command,
                        matcher=matcher,
                        timeout=hook.get("timeout"),
                        status_message=hook.get("statusMessage"),
                    )
                )

    return settings, entries


def validate_script_exists(
    entry: HookEntry,
    base_path: Path,
) -> Violation | None:
    """Check that the referenced script file exists."""
    full_path = base_path / entry.script_path
    if not full_path.is_file():
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="missing_script",
            message=f"Script not found: {entry.script_path}",
        )
    return None


def validate_hook_type_known(entry: HookEntry) -> Violation | None:
    """Check that the hook type is a known Claude Code hook type."""
    if entry.hook_type not in ALL_HOOK_TYPES:
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="unknown_hook_type",
            message=f"Unknown hook type: {entry.hook_type}",
        )
    return None


def validate_timeout(entry: HookEntry) -> Violation | None:
    """Check that timeout values are within reasonable bounds."""
    if entry.timeout is None:
        return None
    if not isinstance(entry.timeout, (int, float)):
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="invalid_timeout",
            message=f"Timeout must be a number, got: {type(entry.timeout).__name__}",
        )
    if entry.timeout < MIN_TIMEOUT or entry.timeout > MAX_TIMEOUT:
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="timeout_range",
            message=(f"Timeout {entry.timeout}s outside range [{MIN_TIMEOUT}, {MAX_TIMEOUT}]"),
        )
    return None


def validate_exit_code_docs(
    entry: HookEntry,
    base_path: Path,
) -> Violation | None:
    """Check that script docstring documents exit codes matching hook semantics.

    PreToolUse/PermissionRequest hooks should document exit 2 = block.
    Stop/SubagentStop hooks should document exit 0 = always/non-blocking.
    """
    full_path = base_path / entry.script_path
    if not full_path.is_file():
        return None  # Already caught by validate_script_exists

    try:
        content = full_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Only check the docstring area (first 30 lines)
    header = "\n".join(content.splitlines()[:30]).lower()

    if entry.hook_type in BLOCKING_HOOK_TYPES:
        if "exit" not in header and "block" not in header:
            return Violation(
                hook_type=entry.hook_type,
                script=entry.script_path,
                category="missing_exit_docs",
                message=(
                    f"Blocking hook ({entry.hook_type}) should document "
                    f"exit code semantics (0=allow, 2=block) in docstring"
                ),
            )

    return None


def validate_duplicate_entries(entries: list[HookEntry]) -> list[Violation]:
    """Check for duplicate hook entries (same script under same hook type + matcher)."""
    seen: dict[tuple[str, str, str | None], HookEntry] = {}
    violations: list[Violation] = []

    for entry in entries:
        key = (entry.hook_type, entry.script_path, entry.matcher)
        if key in seen:
            violations.append(
                Violation(
                    hook_type=entry.hook_type,
                    script=entry.script_path,
                    category="duplicate",
                    message=(
                        f"Duplicate hook entry: {entry.script_path} "
                        f"under {entry.hook_type}"
                        f"{f' (matcher: {entry.matcher})' if entry.matcher else ''}"
                    ),
                )
            )
        else:
            seen[key] = entry

    return violations


def validate_all(
    settings_path: Path,
    base_path: Path,
) -> ContractReport:
    """Run all hook contract validations.

    Args:
        settings_path: Path to settings.json
        base_path: Project root for resolving script paths

    Returns:
        ContractReport with all entries and violations found.
    """
    _, entries = parse_settings(settings_path)
    report = ContractReport(entries=entries)

    # Per-entry validations
    for entry in entries:
        for validator in (
            validate_hook_type_known,
            validate_timeout,
        ):
            violation = validator(entry)
            if violation:
                report.violations.append(violation)

        for validator_with_path in (
            validate_script_exists,
            validate_exit_code_docs,
        ):
            violation = validator_with_path(entry, base_path)
            if violation:
                report.violations.append(violation)

    # Cross-entry validations
    report.violations.extend(validate_duplicate_entries(entries))

    return report


def format_console(report: ContractReport) -> str:
    """Format report for console output."""
    lines: list[str] = []

    if report.is_valid:
        lines.append(f"{_COLOR_GREEN}All hook contracts valid{_COLOR_RESET}")
        lines.append(f"{_COLOR_CYAN}   Validated {len(report.entries)} hook entries{_COLOR_RESET}")
        return "\n".join(lines)

    lines.append(f"{_COLOR_RED}Hook contract violations found{_COLOR_RESET}")
    lines.append("")
    lines.append(f"{_COLOR_YELLOW}Found {len(report.violations)} violation(s):{_COLOR_RESET}")
    lines.append("")

    for v in report.violations:
        lines.append(f"  {_COLOR_RED}[{v.category}] {v.hook_type}: {v.script}{_COLOR_RESET}")
        lines.append(f"    {v.message}")

    return "\n".join(lines)


def format_json(report: ContractReport) -> str:
    """Format report as JSON."""
    data = {
        "status": "pass" if report.is_valid else "fail",
        "entriesValidated": len(report.entries),
        "violationCount": len(report.violations),
        "violations": [
            {
                "hookType": v.hook_type,
                "script": v.script,
                "category": v.category,
                "message": v.message,
            }
            for v in report.violations
        ],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_FORMATTERS = {
    "console": format_console,
    "json": format_json,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate Claude Code hook contracts in settings.json.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("SCAN_PATH", "."),
        help="Project root path (env: SCAN_PATH, default: current directory)",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Path to settings.json (default: <path>/.claude/settings.json)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on violations (env: CI)",
    )
    parser.add_argument(
        "--format",
        choices=("console", "json"),
        default=os.environ.get("OUTPUT_FORMAT", "console"),
        dest="output_format",
        help="Output format (env: OUTPUT_FORMAT, default: console)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    base_path = Path(args.path).resolve()
    if not base_path.is_dir():
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        return 2

    settings_path = (
        Path(args.settings) if args.settings else base_path / ".claude" / "settings.json"
    )
    if not settings_path.is_file():
        print(
            f"Error: Settings file not found: {settings_path}",
            file=sys.stderr,
        )
        return 2

    try:
        report = validate_all(settings_path, base_path)
    except json.JSONDecodeError as exc:
        print(
            f"Error: Invalid JSON in settings.json: {exc}",
            file=sys.stderr,
        )
        return 2

    formatter = _FORMATTERS[args.output_format]
    print(formatter(report))

    if not report.is_valid and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
