#!/usr/bin/env python3
"""CodeQL scan skill wrapper providing unified interface for security analysis.

Supports full scans, quick scans with caching, and configuration validation.
Delegates to underlying CodeQL scripts in .codeql/scripts/.

Exit codes follow ADR-035:
    0 - Success (no findings or findings ignored)
    1 - Findings detected (CI mode only)
    2 - Configuration invalid
    3 - Scan execution failed (CLI not found, script error)
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_COLORS = {
    "success": "\033[32m",
    "error": "\033[31m",
    "warning": "\033[33m",
    "info": "\033[36m",
    "white": "\033[37m",
    "reset": "\033[0m",
}

_PREFIXES = {
    "success": "[ok]",
    "error": "[x]",
    "warning": "[!]",
    "info": "[i]",
}


def _color_print(message: str, msg_type: str = "info") -> None:
    """Print a colored message to stderr."""
    prefix = _PREFIXES.get(msg_type, "[i]")
    color = _COLORS.get(msg_type, _COLORS["info"])
    reset = _COLORS["reset"]
    print(f"{color}{prefix} {message}{reset}", file=sys.stderr)


def _get_repo_root() -> Path | None:
    """Get the git repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CodeQL scan skill wrapper for security analysis.",
    )
    parser.add_argument(
        "--operation",
        choices=["full", "quick", "validate"],
        default="full",
        help="Operation type: full (complete scan), quick (cached), validate (config only)",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=["python", "actions"],
        help="Languages to scan (auto-detected if not specified)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exit with code 1 if findings are detected",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not shutil.which("pwsh"):
        print("[SKIP] pwsh not found. Install PowerShell 7+ for CodeQL scanning.")
        return 0

    repo_root = _get_repo_root()
    if repo_root is None:
        _color_print("Not in a git repository", "error")
        return 3

    codeql_cli_path = repo_root / ".codeql" / "cli" / "codeql"
    if platform.system() == "Windows":
        codeql_cli_path = codeql_cli_path.with_suffix(".exe")

    install_script = repo_root / ".codeql" / "scripts" / "Install-CodeQL.ps1"
    scan_script = repo_root / ".codeql" / "scripts" / "Invoke-CodeQLScan.ps1"
    config_script = repo_root / ".codeql" / "scripts" / "Test-CodeQLConfig.ps1"

    print(f"\n{'=== CodeQL Security Scan ==='}", file=sys.stderr)
    print(f"Operation: {args.operation}", file=sys.stderr)
    print("", file=sys.stderr)

    if args.operation == "validate":
        _color_print("Validating CodeQL configuration...", "info")
        if not config_script.exists():
            _color_print(f"Configuration script not found: {config_script}", "error")
            return 3

        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(config_script)],
            check=False,
        )
        if result.returncode == 0:
            _color_print("Configuration validation passed", "success")
            return 0
        _color_print("Configuration validation failed", "error")
        return 2

    if not codeql_cli_path.exists():
        _color_print(f"CodeQL CLI not found at: {codeql_cli_path}", "error")
        print("", file=sys.stderr)
        _color_print("Install CodeQL CLI with:", "info")
        print(f"  pwsh {install_script} -AddToPath", file=sys.stderr)
        print("", file=sys.stderr)
        _color_print("Or use VSCode task: 'CodeQL: Install CLI'", "info")
        return 3

    _color_print(f"CodeQL CLI found at: {codeql_cli_path}", "success")

    if not scan_script.exists():
        _color_print(f"Scan script not found: {scan_script}", "error")
        return 3

    scan_args: list[str] = ["pwsh", "-NoProfile", "-File", str(scan_script)]

    if args.operation == "quick":
        scan_args.append("-UseCache")
        _color_print("Running quick scan (using cached databases)...", "info")
    else:
        _color_print("Running full scan (rebuilding databases)...", "info")

    if args.languages:
        scan_args.append("-Languages")
        scan_args.extend(args.languages)
        _color_print(f"Scanning languages: {', '.join(args.languages)}", "info")

    if args.ci:
        scan_args.append("-CI")
        _color_print("CI mode enabled (exit 1 on findings)", "info")

    print("", file=sys.stderr)

    result = subprocess.run(scan_args, check=False)
    exit_code = result.returncode

    print("", file=sys.stderr)

    exit_messages = {
        0: ("Scan completed successfully", "success"),
        1: ("Scan completed with findings", "warning"),
        2: ("Configuration error", "error"),
        3: ("Scan execution failed", "error"),
    }

    default_msg = (f"Scan exited with unexpected code: {exit_code}", "warning")
    msg, msg_type = exit_messages.get(exit_code, default_msg)
    _color_print(msg, msg_type)

    if exit_code == 0:
        results_dir = repo_root / ".codeql" / "results"
        if results_dir.exists():
            _color_print("SARIF results: .codeql/results/", "info")
    elif exit_code == 1:
        _color_print("Review SARIF files in .codeql/results/", "info")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
