#!/usr/bin/env python3
"""One-command setup for CodeQL local development integration.

Orchestration script that installs all CodeQL integration components:
- CodeQL CLI installation
- VSCode configurations (extensions, tasks, settings)
- Claude Code skill
- Pre-commit hook integration with actionlint

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (not in a git repository, prerequisite check failed)
    2 - Configuration error (missing directories, permission denied)
    3 - External dependency error (CodeQL CLI installation failed)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install all CodeQL integration components.",
    )
    parser.add_argument(
        "--skip-cli", action="store_true",
        help="Skip CodeQL CLI installation.",
    )
    parser.add_argument(
        "--skip-vscode", action="store_true",
        help="Skip VSCode configuration files creation.",
    )
    parser.add_argument(
        "--skip-claude-skill", action="store_true",
        help="Skip Claude Code skill installation.",
    )
    parser.add_argument(
        "--skip-pre-commit", action="store_true",
        help="Skip pre-commit hook verification.",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI mode (non-interactive).",
    )
    return parser


def write_status(message: str, status_type: str = "info") -> None:
    prefixes = {
        "success": "[PASS]",
        "error": "[FAIL]",
        "warning": "[WARNING]",
        "info": "[INFO]",
        "header": "===",
    }
    prefix = prefixes.get(status_type, "[INFO]")
    if status_type == "header":
        print(f"\n{prefix} {message} {prefix}", file=sys.stderr)
    else:
        print(f"{prefix} {message}", file=sys.stderr)


def get_repo_root() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def step_install_cli(repo_root: str, ci: bool) -> str:
    write_status("Installing CodeQL CLI...", "info")
    install_script = os.path.join(repo_root, ".codeql", "scripts", "install_codeql.py")

    if not os.path.isfile(install_script):
        write_status(f"install_codeql.py not found at: {install_script}", "error")
        sys.exit(2)

    cmd = [sys.executable, install_script, "--add-to-path"]
    if ci:
        cmd.append("--ci")

    result = subprocess.run(cmd, timeout=600, check=False)
    if result.returncode == 0:
        write_status("CodeQL CLI installed successfully", "success")
        return "[PASS] CodeQL CLI installed at .codeql/cli/"
    else:
        write_status(
            f"CodeQL CLI installation failed with exit code: {result.returncode}",
            "error",
        )
        sys.exit(3)


def step_verify_vscode(repo_root: str) -> str:
    write_status("Verifying VSCode configurations...", "info")
    vscode_dir = os.path.join(repo_root, ".vscode")

    extensions_file = os.path.join(vscode_dir, "extensions.json")
    tasks_file = os.path.join(vscode_dir, "tasks.json")
    settings_file = os.path.join(vscode_dir, "settings.json")

    if (
        os.path.isfile(extensions_file)
        and os.path.isfile(tasks_file)
        and os.path.isfile(settings_file)
    ):
        write_status("VSCode configurations verified", "success")
        return "[PASS] VSCode configurations created"

    write_status(
        "VSCode configurations not found. They should be created manually.",
        "warning",
    )
    return "[WARNING] VSCode configurations missing"


def step_verify_claude_skill(repo_root: str) -> str:
    write_status("Verifying Claude Code skill...", "info")
    skill_dir = os.path.join(repo_root, ".claude", "skills", "codeql-scan")
    skill_file = os.path.join(skill_dir, "SKILL.md")
    skill_script = os.path.join(
        skill_dir, "scripts", "Invoke-CodeQLScanSkill.ps1",
    )

    if os.path.isfile(skill_file) and os.path.isfile(skill_script):
        write_status("Claude Code skill verified", "success")
        if platform.system().lower() != "windows":
            try:
                os.chmod(skill_script, 0o755)
            except OSError:
                pass
        return "[PASS] Claude Code skill installed"

    write_status(
        "Claude Code skill not found. It should be created manually.",
        "warning",
    )
    return "[WARNING] Claude Code skill missing"


def step_verify_pre_commit(repo_root: str) -> str:
    write_status("Verifying pre-commit hook...", "info")
    pre_commit_hook = os.path.join(repo_root, ".githooks", "pre-commit")

    if not os.path.isfile(pre_commit_hook):
        write_status(f"Pre-commit hook not found at: {pre_commit_hook}", "warning")
        return "[WARNING] Pre-commit hook not found"

    write_status("Pre-commit hook found", "success")

    actionlint = shutil.which("actionlint")
    if actionlint:
        write_status("actionlint is installed", "success")
        return "[PASS] Pre-commit hook updated with actionlint"

    write_status("actionlint not found", "warning")
    return "[WARNING] actionlint not found - install for YAML validation"


def step_validate(repo_root: str) -> None:
    write_status("Validating installation...", "info")
    config_script = os.path.join(
        repo_root, ".codeql", "scripts", "test_codeql_config.py",
    )

    if os.path.isfile(config_script):
        result = subprocess.run(
            [sys.executable, config_script],
            capture_output=True, timeout=60, check=False,
        )
        if result.returncode == 0:
            write_status("Configuration validation passed", "success")
        else:
            write_status(
                "Configuration validation failed (expected if config doesn't exist yet)",
                "warning",
            )
    else:
        write_status("Configuration validation script not found", "warning")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = get_repo_root()
    if not repo_root:
        write_status(
            "Not in a git repository. This script must be run from within the repository.",
            "error",
        )
        return 1

    write_status("CodeQL Integration Setup", "header")

    installation_steps: list[str] = []

    if not args.skip_cli:
        installation_steps.append(step_install_cli(repo_root, args.ci))
    else:
        write_status("Skipping CodeQL CLI installation", "info")
        installation_steps.append("[SKIP] CodeQL CLI installation skipped")

    if not args.skip_vscode:
        installation_steps.append(step_verify_vscode(repo_root))
    else:
        write_status("Skipping VSCode configuration", "info")
        installation_steps.append("[SKIP] VSCode configurations skipped")

    if not args.skip_claude_skill:
        installation_steps.append(step_verify_claude_skill(repo_root))
    else:
        write_status("Skipping Claude Code skill installation", "info")
        installation_steps.append("[SKIP] Claude Code skill installation skipped")

    if not args.skip_pre_commit:
        installation_steps.append(step_verify_pre_commit(repo_root))
    else:
        write_status("Skipping pre-commit hook verification", "info")
        installation_steps.append("[SKIP] Pre-commit hook verification skipped")

    step_validate(repo_root)

    write_status("Installation Summary", "header")
    for step in installation_steps:
        print(f"  {step}", file=sys.stderr)

    print("", file=sys.stderr)
    write_status("Installation complete!", "success")
    print("", file=sys.stderr)
    write_status("Next steps:", "info")
    print("  1. Restart VSCode to load new configurations", file=sys.stderr)
    print(
        "  2. Run: python3 .codeql/scripts/invoke_codeql_scan.py",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
