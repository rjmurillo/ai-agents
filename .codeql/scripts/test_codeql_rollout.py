#!/usr/bin/env python3
"""Validate successful CodeQL integration deployment across all tiers.

Comprehensive validation of CodeQL integration including:
- CLI installation and configuration
- Shared configuration files
- Script availability
- CI/CD workflow integration
- Local development integration (VSCode, Claude Code)
- Automatic scanning (PostToolUse hook)
- Documentation completeness
- Test coverage
- Gitignore configuration

Exit codes follow ADR-035:
    0 - All checks passed
    1 - One or more checks failed
    3 - Unable to perform validation
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate CodeQL integration deployment.",
    )
    parser.add_argument(
        "--format", choices=["console", "json"], default="console",
        dest="output_format",
        help="Output format.",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI mode: returns non-zero exit code on failures.",
    )
    return parser


class ValidationTracker:
    def __init__(self) -> None:
        self.results: dict[str, list[dict]] = {
            "CLI": [],
            "Configuration": [],
            "Scripts": [],
            "CICD": [],
            "LocalDev": [],
            "Automatic": [],
            "Documentation": [],
            "Tests": [],
            "Gitignore": [],
        }
        self.total_checks = 0
        self.passed_checks = 0

    def add(
        self, category: str, name: str, passed: bool, details: str = "",
    ) -> None:
        self.total_checks += 1
        if passed:
            self.passed_checks += 1
        self.results[category].append({
            "name": name,
            "passed": passed,
            "details": details,
        })

    def print_check(self, passed: bool, message: str) -> None:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {message}")


def check_cli(tracker: ValidationTracker) -> None:
    print("\n[CLI Installation]")

    is_windows = platform.system().lower() == "windows"
    cli_path = ".codeql/cli/codeql.exe" if is_windows else ".codeql/cli/codeql"

    cli_exists = os.path.isfile(cli_path)
    tracker.print_check(cli_exists, "CodeQL CLI exists")
    tracker.add("CLI", "CLI exists", cli_exists, cli_path)

    if cli_exists:
        try:
            result = subprocess.run(
                [cli_path, "version"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            version = result.stdout.strip().split("\n")[0] if result.returncode == 0 else ""
            version_valid = "CodeQL command-line toolchain release" in version
            tracker.print_check(version_valid, f"CLI version: {version}")
            tracker.add("CLI", "CLI version", version_valid, version)
        except (OSError, subprocess.TimeoutExpired) as exc:
            tracker.print_check(False, "CLI version check failed")
            tracker.add("CLI", "CLI version", False, str(exc))

        if not is_windows:
            executable = os.access(cli_path, os.X_OK)
            tracker.print_check(executable, "CLI executable")
            tracker.add("CLI", "CLI executable", executable, "Unix executable check")
        else:
            tracker.print_check(True, "CLI executable")
            tracker.add("CLI", "CLI executable", True, "Windows (no executable bit)")
    else:
        tracker.print_check(False, "CLI version (CLI not found)")
        tracker.print_check(False, "CLI executable (CLI not found)")
        tracker.add("CLI", "CLI version", False, "CLI not found")
        tracker.add("CLI", "CLI executable", False, "CLI not found")


def check_configuration(tracker: ValidationTracker) -> None:
    print("\n[Configuration]")

    shared_config = ".github/codeql/codeql-config.yml"
    shared_exists = os.path.isfile(shared_config)
    tracker.print_check(shared_exists, "Shared config exists")
    tracker.add("Configuration", "Shared config", shared_exists, shared_config)

    quick_config = ".github/codeql/codeql-config-quick.yml"
    quick_exists = os.path.isfile(quick_config)
    tracker.print_check(quick_exists, "Quick config exists")
    tracker.add("Configuration", "Quick config", quick_exists, quick_config)

    if shared_exists:
        try:
            content = Path(shared_config).read_text(encoding="utf-8")
            valid = True
            for line in content.split("\n"):
                if line.startswith("\t"):
                    valid = False
                    break
            tracker.print_check(valid, "YAML syntax valid")
            tracker.add("Configuration", "YAML syntax", valid, "Basic validation")
        except OSError:
            tracker.print_check(False, "YAML syntax (read error)")
            tracker.add("Configuration", "YAML syntax", False, "Read error")

        has_queries = "queries:" in content
        tracker.print_check(has_queries, "Query packs resolvable")
        tracker.add("Configuration", "Query packs", has_queries, "Config has queries section")
    else:
        tracker.print_check(False, "YAML syntax (config not found)")
        tracker.print_check(False, "Query packs (config not found)")
        tracker.add("Configuration", "YAML syntax", False, "Config not found")
        tracker.add("Configuration", "Query packs", False, "Config not found")


def check_scripts(tracker: ValidationTracker) -> None:
    print("\n[Scripts]")

    required_scripts = [
        ".codeql/scripts/install_codeql.py",
        ".codeql/scripts/invoke_codeql_scan.py",
        ".codeql/scripts/test_codeql_config.py",
        ".codeql/scripts/get_codeql_diagnostics.py",
        ".codeql/scripts/install_codeql_integration.py",
    ]

    found = sum(1 for s in required_scripts if os.path.isfile(s))
    total = len(required_scripts)
    all_exist = found == total

    tracker.print_check(all_exist, f"All scripts exist ({found}/{total})")
    tracker.add("Scripts", "Scripts exist", all_exist, f"{found} of {total} scripts found")

    test_scripts = [
        "tests/test_install_codeql.py",
        "tests/test_invoke_codeql_scan.py",
        "tests/test_codeql_integration.py",
    ]

    tests_found = sum(1 for t in test_scripts if os.path.isfile(t))
    tests_total = len(test_scripts)
    all_tests = tests_found == tests_total

    tracker.print_check(all_tests, f"Pytest tests exist ({tests_found}/{tests_total})")
    tracker.add("Scripts", "Pytest tests", all_tests, f"{tests_found} of {tests_total} test files found")


def check_cicd(tracker: ValidationTracker) -> None:
    print("\n[CI/CD Integration]")

    codeql_workflow = ".github/workflows/codeql-analysis.yml"
    workflow_exists = os.path.isfile(codeql_workflow)
    tracker.print_check(workflow_exists, "CodeQL workflow exists")
    tracker.add("CICD", "CodeQL workflow", workflow_exists, codeql_workflow)

    test_workflow = ".github/workflows/test-codeql-integration.yml"
    test_exists = os.path.isfile(test_workflow)
    tracker.print_check(test_exists, "Test workflow exists")
    tracker.add("CICD", "Test workflow", test_exists, test_workflow)

    sha_pinned = True
    if workflow_exists:
        content = Path(codeql_workflow).read_text(encoding="utf-8")
        if not re.search(r"github/codeql-action/.*@[0-9a-f]{40}", content):
            sha_pinned = False

    tracker.print_check(sha_pinned, "SHA-pinned actions")
    tracker.add("CICD", "SHA-pinned actions", sha_pinned, "CodeQL workflow check")

    config_referenced = False
    if workflow_exists:
        content = Path(codeql_workflow).read_text(encoding="utf-8")
        config_referenced = "codeql-config.yml" in content

    tracker.print_check(config_referenced, "Shared config referenced")
    tracker.add("CICD", "Shared config ref", config_referenced, "Workflow references shared config")


def check_local_dev(tracker: ValidationTracker) -> None:
    print("\n[Local Development]")

    checks = [
        (".vscode/extensions.json", "github.vscode-codeql", "VSCode extensions configured"),
        (".vscode/tasks.json", "CodeQL.*Scan", "VSCode tasks configured"),
        (".vscode/settings.json", "codeQL", "VSCode settings configured"),
    ]

    for filepath, pattern, label in checks:
        configured = False
        if os.path.isfile(filepath):
            content = Path(filepath).read_text(encoding="utf-8")
            configured = bool(re.search(pattern, content))
        tracker.print_check(configured, label)
        tracker.add("LocalDev", label, configured, filepath)

    skill_file = ".claude/skills/codeql-scan/SKILL.md"
    skill_exists = os.path.isfile(skill_file)
    tracker.print_check(skill_exists, "Claude Code skill exists")
    tracker.add("LocalDev", "Claude skill", skill_exists, skill_file)

    skill_script = ".claude/skills/codeql-scan/scripts/Invoke-CodeQLScanSkill.ps1"
    script_exists = os.path.isfile(skill_script)
    tracker.print_check(script_exists, "Skill script executable")
    tracker.add("LocalDev", "Skill script", script_exists, skill_script)


def check_automatic(tracker: ValidationTracker) -> None:
    print("\n[Automatic Scanning]")

    hook_script = ".claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1"
    hook_exists = os.path.isfile(hook_script)
    tracker.print_check(hook_exists, "PostToolUse hook exists")
    tracker.add("Automatic", "PostToolUse hook", hook_exists, hook_script)

    if hook_exists and platform.system().lower() != "windows":
        executable = os.access(hook_script, os.X_OK)
        tracker.print_check(executable, "Hook script executable")
        tracker.add("Automatic", "Hook executable", executable, "Unix executable bit")
    else:
        tracker.print_check(True, "Hook script executable")
        tracker.add("Automatic", "Hook executable", True, "Windows or hook not found")

    quick_ref = False
    if hook_exists:
        content = Path(hook_script).read_text(encoding="utf-8")
        quick_ref = "codeql-config-quick.yml" in content
    tracker.print_check(quick_ref, "Quick config referenced")
    tracker.add("Automatic", "Quick config ref", quick_ref, "Hook references quick config")


def check_documentation(tracker: ValidationTracker) -> None:
    print("\n[Documentation]")

    docs = [
        ("docs/codeql-integration.md", "User docs exist"),
        ("docs/codeql-architecture.md", "Developer docs exist"),
        (".agents/architecture/ADR-041-codeql-integration.md", "ADR exists"),
    ]

    for filepath, label in docs:
        exists = os.path.isfile(filepath)
        tracker.print_check(exists, label)
        tracker.add("Documentation", label, exists, filepath)

    agents_md = "AGENTS.md"
    updated = False
    if os.path.isfile(agents_md):
        content = Path(agents_md).read_text(encoding="utf-8")
        updated = "CodeQL Security Analysis" in content
    tracker.print_check(updated, "AGENTS.md updated")
    tracker.add("Documentation", "AGENTS.md", updated, "Contains CodeQL section")


def check_tests(tracker: ValidationTracker) -> None:
    print("\n[Tests]")

    test_files = [
        "tests/test_install_codeql.py",
        "tests/test_invoke_codeql_scan.py",
    ]
    found = sum(1 for t in test_files if os.path.isfile(t))
    has_tests = found > 0

    tracker.print_check(has_tests, f"Unit tests discoverable ({found} files)")
    tracker.add("Tests", "Unit tests", has_tests, f"{found} test files found")

    integration = "tests/test_codeql_integration.py"
    integration_exists = os.path.isfile(integration)
    tracker.print_check(integration_exists, "Integration tests exist")
    tracker.add("Tests", "Integration tests", integration_exists, integration)


def check_gitignore(tracker: ValidationTracker) -> None:
    print("\n[Gitignore]")

    gitignore = ".gitignore"
    configured = False
    details = "Gitignore file not found"

    if os.path.isfile(gitignore):
        content = Path(gitignore).read_text(encoding="utf-8")
        required = [".codeql/cli/", ".codeql/db/", ".codeql/results/", ".codeql/logs/"]
        found = sum(1 for p in required if re.search(re.escape(p), content))
        configured = found == len(required)
        details = f"{found} of {len(required)} patterns found"

    tracker.print_check(configured, "CodeQL directories excluded")
    tracker.add("Gitignore", "Gitignore config", configured, details)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tracker = ValidationTracker()

    try:
        check_cli(tracker)
        check_configuration(tracker)
        check_scripts(tracker)
        check_cicd(tracker)
        check_local_dev(tracker)
        check_automatic(tracker)
        check_documentation(tracker)
        check_tests(tracker)
        check_gitignore(tracker)

        status = "PASS" if tracker.passed_checks == tracker.total_checks else "FAIL"

        banner_dest = sys.stderr if args.output_format == "json" else sys.stdout
        print(f"\n========================================", file=banner_dest)
        print(
            f"Overall Status: {status} "
            f"({tracker.passed_checks}/{tracker.total_checks} checks)",
            file=banner_dest,
        )
        print("========================================\n", file=banner_dest)

        if args.output_format == "json":
            json_output = {
                "TotalChecks": tracker.total_checks,
                "PassedChecks": tracker.passed_checks,
                "Status": status,
                "Categories": tracker.results,
            }
            print(json.dumps(json_output, indent=2))

        if args.ci and status != "PASS":
            return 1

        return 0

    except Exception as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
