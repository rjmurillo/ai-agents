#!/usr/bin/env python3
"""CodeQL scan skill wrapper providing unified interface for security analysis operations.

Wrapper script for CodeQL scanning operations that provides skill-specific functionality
with standardized exit codes (ADR-035) and error handling. Supports full scans, quick
scans with caching, and configuration validation.

Delegates to the Python scripts in ``.codeql/scripts/`` named by
``DELEGATE_SCRIPT_NAMES``. Delegates are launched with ``sys.executable`` so the
child runs in the same interpreter and virtual environment as this wrapper
rather than whatever ``python3`` happens to be first on PATH.

EXIT CODES (ADR-035):
    0 - Success (no findings or findings ignored)
    1 - Findings detected (CI mode only)
    2 - Configuration invalid
    3 - Scan execution failed (CLI not found, script error)

Delegate contracts (see canonical source files for full signatures):

``.codeql/scripts/test_codeql_config.py`` build_parser() (lines 35-53):
    --config-path, --ci
    main() returns 2 when config absent, 0 if valid else 1.

``.codeql/scripts/invoke_codeql_scan.py`` build_parser() (lines 33-78):
    --repo-path, --config-path, --database-path, --results-path,
    --languages, --use-cache, --ci, --format (console|sarif|json), --quick-scan
    Exit codes: 0 success, 1 findings/error, 2 config error, 3 dependency error.

``.codeql/scripts/install_codeql.py`` build_parser():
    parser.add_argument("--add-to-path", action="store_true", ...)

Stricter/looser/different than canonical:
    - Validation collapses delegate exit ``1`` (invalid config) and delegate exit
      ``2`` (config file not found) into this wrapper's single documented ``2 -
      Configuration invalid``. The wrapper contract above has no distinct code
      for a missing config file.
    - ``quick`` maps to the delegate's ``--use-cache`` only, not to its separate
      ``--quick-scan`` flag, which would swap in a different query set.
    - Delegates run with ``cwd`` set to the repository root so their relative
      defaults resolve against the repository instead of the caller's working
      directory. This wrapper therefore does not restate those default paths.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

VALID_OPERATIONS = ("full", "quick", "validate")
VALID_LANGUAGES = ("python", "actions")

CONFIG_SCRIPT_NAME = "test_codeql_config.py"
SCAN_SCRIPT_NAME = "invoke_codeql_scan.py"
INSTALL_SCRIPT_NAME = "install_codeql.py"

#: Delegate scripts this wrapper resolves under ``<repo root>/.codeql/scripts/``.
#: `tests/skills/codeql-scan/test_codeql_delegate_paths.py` asserts every name
#: here resolves to a real file in this repository, so a rename that is not
#: mirrored in `.codeql/scripts/` fails the suite instead of only failing at run
#: time (Issue #4921).
DELEGATE_SCRIPT_NAMES = (CONFIG_SCRIPT_NAME, SCAN_SCRIPT_NAME, INSTALL_SCRIPT_NAME)


def get_repo_root() -> str | None:
    """Get the current worktree root path, or None outside a working tree.

    Uses --show-toplevel, not --git-common-dir. In a LINKED worktree the
    common dir is the MAIN checkout's shared .git, so dirname(common-dir)
    is the main checkout, not this worktree (#2373). --show-toplevel returns
    the current worktree root in every layout and fails in a bare repository.
    Canonical reference: scripts/github_core/repo.py::get_repo_root.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            raw = result.stdout.strip()
            if not raw:
                return None
            toplevel = Path(raw)
            if not toplevel.is_absolute():
                toplevel = (Path.cwd() / toplevel).resolve()
            else:
                toplevel = toplevel.resolve()
            return str(toplevel)
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


def _python_executable() -> str:
    """Return the interpreter used to launch delegate scripts.

    ``sys.executable`` is documented to be an empty string when the interpreter
    cannot determine a real executable path (frozen or embedded builds). The
    fallback keeps the delegate command well formed instead of building a
    command whose first element is ``""``.
    """
    return sys.executable or "python3"


def _delegate_path(repo_root: str, script_name: str) -> str:
    """Resolve a delegate script under ``<repo root>/.codeql/scripts/``."""
    return os.path.join(repo_root, ".codeql", "scripts", script_name)


def _run_delegate(command: list[str], repo_root: str, timeout: int) -> int | None:
    """Run a delegate script from the repository root.

    Returns the delegate's exit code, or None when the interpreter could not be
    launched or the delegate timed out, which the caller reports as exit 3.
    """
    try:
        sys.stdout.flush()
        result = subprocess.run(command, cwd=repo_root, timeout=timeout, check=False)
    except OSError as exc:
        write_colored(f"Could not run {command[0]}: {exc}", "error")
        return None
    except subprocess.TimeoutExpired:
        write_colored(f"Delegate timed out after {timeout}s: {command[1]}", "error")
        return None
    return result.returncode


def _validate_config(repo_root: str) -> int:
    """Validate the CodeQL configuration via the config delegate."""
    write_colored("Validating CodeQL configuration...", "info")
    config_script = _delegate_path(repo_root, CONFIG_SCRIPT_NAME)
    if not Path(config_script).exists():
        write_colored(f"Configuration script not found: {config_script}", "error")
        return 3

    returncode = _run_delegate(
        [_python_executable(), config_script], repo_root, timeout=120
    )
    if returncode is None:
        return 3
    if returncode == 0:
        write_colored("Configuration validation passed", "success")
        return 0
    write_colored("Configuration validation failed", "error")
    return 2


def _build_scan_command(
    scan_script: str,
    operation: str,
    languages: list[str] | None,
    ci_mode: bool,
) -> list[str]:
    """Build the delegate scan command and report the selected options."""
    command = [_python_executable(), scan_script]

    if operation == "quick":
        command.append("--use-cache")
        write_colored("Running quick scan (using cached databases)...", "info")
    else:
        write_colored("Running full scan (rebuilding databases)...", "info")

    if languages:
        command.append("--languages")
        command.extend(languages)
        write_colored(f"Scanning languages: {', '.join(languages)}", "info")

    if ci_mode:
        command.append("--ci")
        write_colored("CI mode enabled (exit 1 on findings)", "info")

    return command


def _report_scan_outcome(exit_code: int, repo_root: str) -> None:
    """Print a human-readable summary for a delegate scan exit code."""
    exit_messages = {
        0: ("Scan completed successfully", "success"),
        1: ("Scan completed with findings", "warning"),
        2: ("Configuration error", "error"),
        3: ("Scan execution failed", "error"),
    }

    default_msg = (f"Scan exited with unexpected code: {exit_code}", "warning")
    msg, msg_type = exit_messages.get(exit_code, default_msg)
    write_colored(msg, msg_type)

    if exit_code == 0:
        if Path(os.path.join(repo_root, ".codeql", "results")).exists():
            write_colored("SARIF results: .codeql/results/", "info")
    elif exit_code == 1:
        write_colored("Review SARIF files in .codeql/results/", "info")


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

    print("\n=== CodeQL Security Scan ===", file=sys.stderr)
    print(f"Operation: {operation}", file=sys.stderr)
    print("", file=sys.stderr)

    if operation == "validate":
        return _validate_config(repo_root)

    codeql_cli_path = os.path.join(repo_root, ".codeql", "cli", "codeql")
    if sys.platform == "win32":
        codeql_cli_path += ".exe"

    if not Path(codeql_cli_path).exists():
        write_colored(f"CodeQL CLI not found at: {codeql_cli_path}", "error")
        print("", file=sys.stderr)
        write_colored("Install CodeQL CLI with:", "info")
        install_script = _delegate_path(repo_root, INSTALL_SCRIPT_NAME)
        print(
            f"  {_python_executable()} {install_script} --add-to-path",
            file=sys.stderr,
        )
        return 3

    write_colored(f"CodeQL CLI found at: {codeql_cli_path}", "success")

    scan_script = _delegate_path(repo_root, SCAN_SCRIPT_NAME)
    if not Path(scan_script).exists():
        write_colored(f"Scan script not found: {scan_script}", "error")
        return 3

    command = _build_scan_command(scan_script, operation, languages, ci_mode)
    print("", file=sys.stderr)

    exit_code = _run_delegate(command, repo_root, timeout=600)
    if exit_code is None:
        return 3

    print("", file=sys.stderr)
    _report_scan_outcome(exit_code, repo_root)
    return exit_code


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
