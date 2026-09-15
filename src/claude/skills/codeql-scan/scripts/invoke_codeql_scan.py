#!/usr/bin/env python3
"""CodeQL scan skill wrapper providing unified interface for security analysis.

Supports full scans, quick scans with caching, and configuration validation.
Delegates to the Python scripts in ``.codeql/scripts/`` named by
``DELEGATE_SCRIPT_NAMES``. Delegates are launched with ``sys.executable`` so the
child runs in the same interpreter and virtual environment as this wrapper
rather than whatever ``python3`` happens to be first on PATH.

Exit codes follow ADR-035:
    0 - Success (no findings or findings ignored)
    1 - Findings detected (CI mode only)
    2 - Configuration invalid
    3 - Scan execution failed (CLI not found, script error)

Delegate contracts (see canonical source files for full signatures):

``.codeql/scripts/test_codeql_config.py`` build_parser() (lines 35-53):
    --config-path, --ci, --format (console|json)
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
    - ``--operation quick`` maps to the delegate's ``--use-cache`` only, not to
      its separate ``--quick-scan`` flag. ``--quick-scan`` swaps the config file
      for ``codeql-config-quick.yml`` (a different query set); this wrapper's
      documented meaning of "quick" is "cached databases", so it reuses caches
      against the same query set.
    - Delegates run with ``cwd`` set to the repository root so their relative
      defaults (``.github/codeql/codeql-config.yml``, ``.codeql/db``,
      ``.codeql/results``, and ``--repo-path .``) resolve against the repository
      instead of the caller's working directory. This wrapper therefore does not
      restate those default paths.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

CONFIG_SCRIPT_NAME = "test_codeql_config.py"
SCAN_SCRIPT_NAME = "invoke_codeql_scan.py"
INSTALL_SCRIPT_NAME = "install_codeql.py"

#: Delegate scripts this wrapper resolves under ``<repo root>/.codeql/scripts/``.
#: `tests/skills/codeql-scan/test_codeql_delegate_paths.py` asserts every name
#: here resolves to a real file in this repository, so a rename that is not
#: mirrored in `.codeql/scripts/` fails the suite instead of only failing at run
#: time (Issue #4921).
DELEGATE_SCRIPT_NAMES = (CONFIG_SCRIPT_NAME, SCAN_SCRIPT_NAME, INSTALL_SCRIPT_NAME)

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
    """Get the current worktree root, or None outside a working tree.

    Uses --show-toplevel, not --git-common-dir. In a LINKED worktree the
    common dir is the MAIN checkout's shared .git, so dirname(common-dir)
    is the main checkout, not this worktree (#2373). --show-toplevel returns
    the current worktree root in every layout and fails (returncode != 0) in
    a bare repository, where the caller surfaces a clear "not in a git
    repository" error (exit 3). Canonical reference:
    scripts/github_core/repo.py::get_repo_root.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    toplevel = Path(raw)
    if not toplevel.is_absolute():
        toplevel = (Path.cwd() / toplevel).resolve()
    else:
        toplevel = toplevel.resolve()
    return toplevel


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


def _python_executable() -> str:
    """Return the interpreter used to launch delegate scripts.

    ``sys.executable`` is documented to be an empty string when the interpreter
    cannot determine a real executable path (frozen or embedded builds). The
    fallback keeps the delegate command well formed instead of building a
    command whose first element is ``""``.
    """
    return sys.executable or "python3"


def _delegate_path(repo_root: Path, script_name: str) -> Path:
    """Resolve a delegate script under ``<repo root>/.codeql/scripts/``."""
    return repo_root / ".codeql" / "scripts" / script_name


def _run_delegate(command: list[str], repo_root: Path) -> int | None:
    """Run a delegate script from the repository root.

    Returns the delegate's exit code, or None when the interpreter could not be
    launched, which the caller reports as exit 3.
    """
    try:
        sys.stdout.flush()
        result = subprocess.run(command, cwd=str(repo_root), check=False)
    except OSError as exc:
        _color_print(f"Could not run {command[0]}: {exc}", "error")
        return None
    return result.returncode


def _validate_config(repo_root: Path) -> int:
    """Validate the CodeQL configuration via the config delegate."""
    _color_print("Validating CodeQL configuration...", "info")
    config_script = _delegate_path(repo_root, CONFIG_SCRIPT_NAME)
    if not config_script.exists():
        _color_print(f"Configuration script not found: {config_script}", "error")
        return 3

    returncode = _run_delegate(
        [_python_executable(), str(config_script)], repo_root
    )
    if returncode is None:
        return 3
    if returncode == 0:
        _color_print("Configuration validation passed", "success")
        return 0
    _color_print("Configuration validation failed", "error")
    return 2


def _build_scan_command(scan_script: Path, args: argparse.Namespace) -> list[str]:
    """Build the delegate scan command and report the selected options."""
    command = [_python_executable(), str(scan_script)]

    if args.operation == "quick":
        command.append("--use-cache")
        _color_print("Running quick scan (using cached databases)...", "info")
    else:
        _color_print("Running full scan (rebuilding databases)...", "info")

    if args.languages:
        command.append("--languages")
        command.extend(args.languages)
        _color_print(f"Scanning languages: {', '.join(args.languages)}", "info")

    if args.ci:
        command.append("--ci")
        _color_print("CI mode enabled (exit 1 on findings)", "info")

    return command


def _report_scan_outcome(exit_code: int, repo_root: Path) -> None:
    """Print a human-readable summary for a delegate scan exit code."""
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
        if (repo_root / ".codeql" / "results").exists():
            _color_print("SARIF results: .codeql/results/", "info")
    elif exit_code == 1:
        _color_print("Review SARIF files in .codeql/results/", "info")


def _run_scan(repo_root: Path, args: argparse.Namespace) -> int:
    """Run a full or quick scan via the scan delegate."""
    codeql_cli_path = repo_root / ".codeql" / "cli" / "codeql"
    if platform.system() == "Windows":
        codeql_cli_path = codeql_cli_path.with_suffix(".exe")

    if not codeql_cli_path.exists():
        _color_print(f"CodeQL CLI not found at: {codeql_cli_path}", "error")
        print("", file=sys.stderr)
        _color_print("Install CodeQL CLI with:", "info")
        install_script = _delegate_path(repo_root, INSTALL_SCRIPT_NAME)
        print(
            f"  {_python_executable()} {install_script} --add-to-path",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        _color_print("Or use VSCode task: 'CodeQL: Install CLI'", "info")
        return 3

    _color_print(f"CodeQL CLI found at: {codeql_cli_path}", "success")

    scan_script = _delegate_path(repo_root, SCAN_SCRIPT_NAME)
    if not scan_script.exists():
        _color_print(f"Scan script not found: {scan_script}", "error")
        return 3

    command = _build_scan_command(scan_script, args)
    print("", file=sys.stderr)

    exit_code = _run_delegate(command, repo_root)
    if exit_code is None:
        return 3

    print("", file=sys.stderr)
    _report_scan_outcome(exit_code, repo_root)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = _get_repo_root()
    if repo_root is None:
        _color_print("Not in a git repository", "error")
        return 3

    if not (repo_root / ".codeql").exists():
        print("[SKIP] .codeql/ not found. CodeQL scanning requires project setup.", file=sys.stderr)
        return 0

    print("\n=== CodeQL Security Scan ===", file=sys.stderr)
    print(f"Operation: {args.operation}", file=sys.stderr)
    print("", file=sys.stderr)

    if args.operation == "validate":
        return _validate_config(repo_root)

    return _run_scan(repo_root, args)


if __name__ == "__main__":
    raise SystemExit(main())
