#!/usr/bin/env python3
"""Unified shift-left validation runner for pre-PR checks.

Runs all local validations before creating a pull request.
Executes validations in optimized order (fast checks first).

Validation sequence:
    1. Session End (for latest session log)
    2. Pester Tests (all unit tests)
    3. Markdown Lint (auto-fix and validate)
    4. Workflow YAML (validate GitHub Actions workflows)
    5. YAML Style (check YAML style with yamllint) [skip if --quick]
    6. Path Normalization (check for absolute paths) [skip if --quick, requires PS1]
    7. Planning Artifacts (validate planning consistency) [skip if --quick, requires PS1]
    8. Agent Drift (detect semantic drift) [skip if --quick, requires PS1]

Exit codes follow ADR-035:
    0 - Success (all validations passed)
    1 - Logic error (one or more validations failed)
    2 - Config error (environment or configuration issue)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ValidationRecord:
    """Result of a single validation step."""

    name: str
    status: str  # PASS, FAIL, SKIP
    duration: float = 0.0
    message: str = ""


@dataclass
class ValidationState:
    """Tracks overall validation results."""

    results: list[ValidationRecord] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def _find_latest_session_log(repo_root: Path) -> Path | None:
    """Find the most recent session log in .agents/sessions/."""
    sessions_path = repo_root / ".agents" / "sessions"
    if not sessions_path.is_dir():
        return None

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-session-\d+.*\.(?:md|json)$")
    candidates = sorted(
        (f for f in sessions_path.iterdir() if f.is_file() and pattern.match(f.name)),
        key=lambda f: f.name,
        reverse=True,
    )

    return candidates[0] if candidates else None


def _run_subprocess(
    args: list[str], timeout: int = 300
) -> tuple[int, str, str]:
    """Run a subprocess and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"


def run_validation(
    name: str,
    state: ValidationState,
    callback: Callable[[], bool],
    skip: bool = False,
) -> bool:
    """Run a validation and track results. Returns True on pass/skip."""
    state.total += 1

    if skip:
        print(f"[SKIP] {name} (skipped due to --quick flag)")
        state.skipped += 1
        state.results.append(ValidationRecord(name=name, status="SKIP", message="Skipped"))
        return True

    print()
    print(f"=== {name} ===")
    print("[RUNNING] Starting validation...")

    start = time.monotonic()
    success = False
    message = ""

    try:
        success = callback()
        message = "Validation passed" if success else "Validation failed"
    except Exception as exc:
        success = False
        message = f"Validation error: {exc}"

    duration = time.monotonic() - start

    if success:
        state.passed += 1
    else:
        state.failed += 1

    state.results.append(
        ValidationRecord(
            name=name,
            status="PASS" if success else "FAIL",
            duration=duration,
            message=message,
        )
    )

    print()
    status_label = "PASS" if success else "FAIL"
    print(f"[{status_label}] {name} completed in {duration:.2f}s")
    if not success:
        print(f"Error: {message}")

    return success


# ---------------------------------------------------------------------------
# Individual validations
# ---------------------------------------------------------------------------


def validate_session_end(repo_root: Path) -> bool:
    """Validate the latest session log."""
    session_log = _find_latest_session_log(repo_root)
    if session_log is None:
        print("[WARNING] No session log found in .agents/sessions/")
        print("  If this is an agent session, create a session log.")
        print("  If this is a manual commit, this check can be skipped.")
        return True

    print(f"Latest session log: {session_log.name}")

    script = repo_root / "scripts" / "Validate-Session.ps1"
    if not script.exists():
        print("[FAIL] Validate-Session.ps1 not found")
        return False

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-SessionLogPath", str(session_log)]
    )
    return exit_code == 0


def validate_pester_tests(repo_root: Path, verbose: bool = False) -> bool:
    """Run Pester unit tests."""
    script = repo_root / "build" / "scripts" / "Invoke-PesterTests.ps1"
    if not script.exists():
        print("[FAIL] Invoke-PesterTests.ps1 not found")
        return False

    verbosity = "Diagnostic" if verbose else "Normal"
    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-Verbosity", verbosity]
    )
    return exit_code == 0


def validate_markdown_lint(repo_root: Path) -> bool:
    """Run markdownlint auto-fix and validate."""
    if not shutil.which("npx"):
        print("[FAIL] npx not found (Node.js required)")
        print("  Install Node.js: https://nodejs.org/")
        return False

    print("Auto-fixing markdown files...")
    exit_code, _, _ = _run_subprocess(["npx", "markdownlint-cli2", "--fix", "**/*.md"])

    if exit_code != 0:
        print("[FAIL] Markdown linting failed (some issues cannot be auto-fixed)")
        print()
        print("Common unfixable issues:")
        print("  - MD040: Add language identifier to code blocks")
        print("  - MD033: Wrap generic types like ArrayPool<T> in backticks")
        return False

    return True


def validate_workflow_yaml(repo_root: Path) -> bool:
    """Validate GitHub Actions workflow files with actionlint."""
    if not shutil.which("actionlint"):
        print("[WARNING] actionlint not found (workflow validation skipped)")
        print("  Install actionlint to enable GitHub Actions workflow validation.")
        return True

    workflow_path = repo_root / ".github" / "workflows"
    if not workflow_path.is_dir():
        print("[WARNING] No .github/workflows directory found")
        return True

    workflow_files = list(workflow_path.glob("*.yml")) + list(
        workflow_path.glob("*.yaml")
    )
    if not workflow_files:
        print("[WARNING] No workflow files found in .github/workflows/")
        return True

    print(f"Validating {len(workflow_files)} workflow file(s)...")

    exit_code, stdout, stderr = _run_subprocess(
        ["actionlint"] + [str(f) for f in workflow_files]
    )

    if exit_code != 0:
        print("[FAIL] actionlint found issues in workflow files")
        output = stdout or stderr
        lines = output.strip().split("\n")
        for line in lines[:20]:
            print(line)
        if len(lines) > 20:
            print(f"... ({len(lines) - 20} more lines omitted)")
        return False

    print("All workflow files validated successfully.")
    return True


def validate_yaml_style(repo_root: Path) -> bool:
    """Check YAML style with yamllint."""
    if not shutil.which("yamllint"):
        print("[WARNING] yamllint not found (YAML style validation skipped)")
        return True

    print("Checking YAML files for style issues...")
    exit_code, stdout, stderr = _run_subprocess(
        ["yamllint", "-f", "parsable", str(repo_root)]
    )

    if exit_code != 0:
        print("[WARNING] yamllint found style issues (non-blocking)")
        output = stdout or stderr
        lines = output.strip().split("\n")
        for line in lines[:30]:
            print(line)
        if len(lines) > 30:
            print(f"... ({len(lines) - 30} more issues omitted)")
        print()
        print("Note: These are warnings, not errors. Fix when convenient.")
        return True

    print("All YAML files conform to style guidelines.")
    return True


def validate_path_normalization(repo_root: Path) -> bool:
    """Check for absolute paths."""
    script = repo_root / "build" / "scripts" / "Validate-PathNormalization.ps1"
    if not script.exists():
        print("[FAIL] Validate-PathNormalization.ps1 not found")
        return False

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-FailOnViolation"]
    )
    return exit_code == 0


def validate_planning_artifacts(repo_root: Path) -> bool:
    """Validate planning consistency."""
    script = repo_root / "build" / "scripts" / "Validate-PlanningArtifacts.ps1"
    if not script.exists():
        print("[FAIL] Validate-PlanningArtifacts.ps1 not found")
        return False

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-FailOnError"]
    )
    return exit_code == 0


def validate_agent_drift(repo_root: Path) -> bool:
    """Detect agent semantic drift."""
    script = repo_root / "build" / "scripts" / "Detect-AgentDrift.ps1"
    if not script.exists():
        print("[FAIL] Detect-AgentDrift.ps1 not found")
        return False

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script)]
    )
    return exit_code == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Unified shift-left validation runner for pre-PR checks.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=os.environ.get("QUICK_MODE", "").lower() in ("true", "1"),
        help="Skip slow validations (path normalization, planning, drift)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        default=os.environ.get("SKIP_TESTS", "").lower() in ("true", "1"),
        help="Skip Pester unit tests (use sparingly)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Run with verbose output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent.parent
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2

    quick = args.quick
    mode = "Quick (fast checks only)" if quick else "Full"
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=== Pre-PR Validation Runner ===")
    print(f"Repository: {repo_root}")
    print(f"Mode: {mode}")
    print(f"Started: {now}")
    print()

    state = ValidationState()
    start_time = time.monotonic()

    # 1. Session End
    run_validation(
        "Session End Validation",
        state,
        lambda: validate_session_end(repo_root),
    )

    # 2. Pester Tests
    if not args.skip_tests:
        run_validation(
            "Pester Unit Tests",
            state,
            lambda: validate_pester_tests(repo_root, args.verbose),
        )
    else:
        print("[SKIP] Pester Unit Tests (skipped via --skip-tests)")
        state.total += 1
        state.skipped += 1

    # 3. Markdown Lint
    run_validation(
        "Markdown Linting",
        state,
        lambda: validate_markdown_lint(repo_root),
    )

    # 3.5 Workflow YAML
    run_validation(
        "Workflow YAML Validation",
        state,
        lambda: validate_workflow_yaml(repo_root),
    )

    # 3.9 YAML Style (skip if quick)
    run_validation(
        "YAML Style Validation",
        state,
        lambda: validate_yaml_style(repo_root),
        skip=quick,
    )

    # 4. Path Normalization (skip if quick)
    run_validation(
        "Path Normalization",
        state,
        lambda: validate_path_normalization(repo_root),
        skip=quick,
    )

    # 5. Planning Artifacts (skip if quick)
    run_validation(
        "Planning Artifacts",
        state,
        lambda: validate_planning_artifacts(repo_root),
        skip=quick,
    )

    # 6. Agent Drift (skip if quick)
    run_validation(
        "Agent Drift Detection",
        state,
        lambda: validate_agent_drift(repo_root),
        skip=quick,
    )

    total_duration = time.monotonic() - start_time

    # Summary
    print()
    print("=== Validation Summary ===")
    print(f"Duration: {total_duration:.2f}s")
    print(f"Total Validations: {state.total}")
    print(f"Passed: {state.passed}")
    print(f"Failed: {state.failed}")
    print(f"Skipped: {state.skipped}")
    print()

    print("=== Detailed Results ===")
    print()
    for record in state.results:
        duration_str = f" ({record.duration:.2f}s)" if record.duration > 0 else ""
        print(f"[{record.status}] {record.name}{duration_str}")

    print()

    if state.failed > 0:
        print(f"RESULT: {state.failed} validation(s) failed")
        print()
        print("Fix suggestions:")
        print("  1. Review error messages above for specific issues")
        print("  2. Run individual validation scripts for more details")
        print("  3. See .agents/SHIFT-LEFT.md for workflow documentation")
        print()
        return 1

    print("RESULT: All validations passed")
    print()
    print("Ready to create pull request!")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
