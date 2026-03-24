#!/usr/bin/env python3
"""CodeQL scan skill wrapper providing unified interface for security analysis operations.

Wrapper script for CodeQL scanning operations that provides skill-specific functionality
with standardized exit codes (ADR-035) and error handling. Supports full scans, quick
scans with caching, and configuration validation.

EXIT CODES (ADR-035):
    0 - Success (no findings or findings ignored)
    1 - Findings detected (CI mode only)
    2 - Configuration invalid
    3 - Scan execution failed (CLI not found, script error)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

VALID_OPERATIONS = ("full", "quick", "validate")
VALID_LANGUAGES = ("python", "actions")


def get_repo_root() -> str | None:
    """Get the git repository root path."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            git_common = Path(result.stdout.strip())
            if not git_common.is_absolute():
                git_common = (Path.cwd() / git_common).resolve()
            else:
                git_common = git_common.resolve()
            return str(git_common.parent)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def write_colored(message: str, msg_type: str = "info") -> None:
    """Write a message with a type prefix to stderr for status messages."""
    prefixes = {
        "success": "[PASS]",
        "error": "[FAIL]",
        "warning": "[WARNING]",
        "info": "[INFO]",
    }
    prefix = prefixes.get(msg_type, "[INFO]")
    print(f"{prefix} {message}", file=sys.stderr)


def run_scan(
    operation: str = "full",
    languages: list[str] | None = None,
    ci_mode: bool = False,
) -> int:
    """Run CodeQL scan with the specified operation."""
    repo_root = get_repo_root()
    if not repo_root:
        write_colored("Not in a git repository", "error")
        return 3

    codeql_cli_path = os.path.join(repo_root, ".codeql", "cli", "codeql")
    if sys.platform == "win32":
        codeql_cli_path += ".exe"

    install_script = os.path.join(repo_root, ".codeql", "scripts", "Install-CodeQL.ps1")
    scan_script = os.path.join(repo_root, ".codeql", "scripts", "Invoke-CodeQLScan.ps1")
    config_script = os.path.join(repo_root, ".codeql", "scripts", "Test-CodeQLConfig.ps1")

    print(f"\n=== CodeQL Security Scan ===", file=sys.stderr)
    print(f"Operation: {operation}", file=sys.stderr)
    print("", file=sys.stderr)

    if operation == "validate":
        write_colored("Validating CodeQL configuration...", "info")
        if not Path(config_script).exists():
            write_colored(f"Configuration script not found: {config_script}", "error")
            return 3
        try:
            result = subprocess.run(
                ["pwsh", "-NoProfile", "-File", config_script],
                timeout=120,
            )
            if result.returncode == 0:
                write_colored("Configuration validation passed", "success")
                return 0
            write_colored("Configuration validation failed", "error")
            return 2
        except FileNotFoundError:
            write_colored("pwsh not found", "error")
            return 3
        except subprocess.TimeoutExpired:
            write_colored("Configuration validation timed out", "error")
            return 3

    if not Path(codeql_cli_path).exists():
        write_colored(f"CodeQL CLI not found at: {codeql_cli_path}", "error")
        print("", file=sys.stderr)
        write_colored(f"Install CodeQL CLI with:", "info")
        print(f"  pwsh {install_script} -AddToPath", file=sys.stderr)
        return 3

    write_colored(f"CodeQL CLI found at: {codeql_cli_path}", "success")

    if not Path(scan_script).exists():
        write_colored(f"Scan script not found: {scan_script}", "error")
        return 3

    scan_args = ["pwsh", "-NoProfile", "-File", scan_script]

    if operation == "quick":
        scan_args.append("-UseCache")
        write_colored("Running quick scan (using cached databases)...", "info")
    else:
        write_colored("Running full scan (rebuilding databases)...", "info")

    if languages:
        scan_args.append("-Languages")
        scan_args.extend(languages)
        write_colored(f"Scanning languages: {', '.join(languages)}", "info")

    if ci_mode:
        scan_args.append("-CI")
        write_colored("CI mode enabled (exit 1 on findings)", "info")

    print("", file=sys.stderr)

    try:
        result = subprocess.run(scan_args, timeout=600)
        exit_code = result.returncode

        print("", file=sys.stderr)

        if exit_code == 0:
            write_colored("Scan completed successfully", "success")
            results_dir = os.path.join(repo_root, ".codeql", "results")
            if Path(results_dir).exists():
                write_colored("SARIF results: .codeql/results/", "info")
        elif exit_code == 1:
            write_colored("Scan completed with findings", "warning")
            write_colored("Review SARIF files in .codeql/results/", "info")
        elif exit_code == 2:
            write_colored("Configuration error", "error")
        elif exit_code == 3:
            write_colored("Scan execution failed", "error")
        else:
            write_colored(f"Scan exited with unexpected code: {exit_code}", "warning")

        return exit_code

    except FileNotFoundError:
        write_colored("pwsh not found", "error")
        return 3
    except subprocess.TimeoutExpired:
        write_colored("Scan timed out", "error")
        return 3


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="CodeQL scan skill wrapper")
    parser.add_argument(
        "--operation",
        choices=VALID_OPERATIONS,
        default="full",
        help="Operation type: full, quick, or validate",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        choices=VALID_LANGUAGES,
        help="Languages to scan (auto-detected if not specified)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Enable CI mode (exit 1 on findings)",
    )
    args = parser.parse_args()

    return run_scan(
        operation=args.operation,
        languages=args.languages,
        ci_mode=args.ci,
    )


if __name__ == "__main__":
    sys.exit(main())
