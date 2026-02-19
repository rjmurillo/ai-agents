#!/usr/bin/env python3
"""
Skill Eval - Self-healing skill training loop.

Runs skills in real environments, captures structured error bundles,
and feeds them to Claude Code for iterative fixes.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ErrorBundle:
    """Structured error bundle for Claude Code."""

    bundle_id: str
    skill_name: str
    skill_path: str
    target: str
    scenario: str
    iteration: int
    error_type: str
    error_message: str
    stack_trace: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    previous_attempts: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


@dataclass
class EvalResult:
    """Result of an eval run."""

    success: bool
    iterations: int
    duration_ms: int
    final_error: str | None
    changes_made: list[str]
    bundle_history: list[ErrorBundle]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run skill eval loop with Claude Code feedback"
    )
    parser.add_argument("skill_path", type=Path, help="Path to skill directory")
    parser.add_argument(
        "--scenario", type=str, help="Test scenario description", default=None
    )
    parser.add_argument(
        "--target",
        choices=["browser", "browser-headed", "shell", "api"],
        default="shell",
        help="Execution target",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=10, help="Maximum fix iterations"
    )
    parser.add_argument(
        "--timeout", type=int, default=60, help="Execution timeout in seconds"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would execute"
    )
    parser.add_argument(
        "--headed", action="store_true", help="Run browser in headed mode"
    )
    parser.add_argument("--cwd", type=Path, help="Working directory for shell target")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for bundles/reports",
    )
    return parser.parse_args()


def setup_output_dir(skill_path: Path, output_dir: Path | None) -> Path:
    """Create output directory structure."""
    if output_dir is None:
        output_dir = skill_path / ".skill-eval"

    (output_dir / "bundles").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)
    (output_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    return output_dir


def detect_scenario(skill_path: Path) -> str | None:
    """Try to detect test scenario from skill config."""
    config_path = skill_path / ".skill-eval" / "config.yaml"
    if config_path.exists():
        # Would parse YAML here
        pass

    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text()
        # Could extract example usage from SKILL.md
        if "## Quick Start" in content or "## Examples" in content:
            return "Run skill with default parameters"

    return None


def run_shell_skill(
    skill_path: Path, scenario: str, timeout: int, cwd: Path | None
) -> tuple[bool, dict]:
    """Execute a shell-based skill."""
    # Look for main script
    scripts = list((skill_path / "scripts").glob("*.py")) + list(
        (skill_path / "scripts").glob("*.sh")
    )

    if not scripts:
        return False, {
            "error_type": "NoScript",
            "error_message": "No executable script found in skill/scripts/",
            "stack_trace": "",
            "exit_code": 127,
            "stdout": "",
            "stderr": "No scripts found",
        }

    main_script = scripts[0]
    work_dir = cwd or skill_path

    start_time = time.time()
    try:
        result = subprocess.run(
            [sys.executable if main_script.suffix == ".py" else "bash", str(main_script)],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.time() - start_time) * 1000)

        return result.returncode == 0, {
            "error_type": "ExitCode" if result.returncode != 0 else None,
            "error_message": result.stderr[:500] if result.returncode != 0 else "",
            "stack_trace": result.stderr if result.returncode != 0 else "",
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:2000],
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return False, {
            "error_type": "Timeout",
            "error_message": f"Script timed out after {timeout}s",
            "stack_trace": "",
            "exit_code": 124,
            "stdout": e.stdout[:2000] if e.stdout else "",
            "stderr": e.stderr[:2000] if e.stderr else "",
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return False, {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "stack_trace": "",
            "exit_code": 1,
            "stdout": "",
            "stderr": str(e),
            "duration_ms": duration_ms,
        }


def run_browser_skill(
    skill_path: Path, scenario: str, timeout: int, headed: bool
) -> tuple[bool, dict]:
    """Execute a browser-based skill (placeholder for Playwright integration)."""
    # TODO: Implement Playwright-based execution
    return False, {
        "error_type": "NotImplemented",
        "error_message": "Browser execution target not yet implemented",
        "stack_trace": "",
        "exit_code": 1,
        "stdout": "",
        "stderr": "Browser target requires Playwright integration",
        "duration_ms": 0,
    }


def create_error_bundle(
    skill_path: Path,
    target: str,
    scenario: str,
    iteration: int,
    error_data: dict,
    previous_attempts: list[dict],
) -> ErrorBundle:
    """Create structured error bundle."""
    return ErrorBundle(
        bundle_id=f"eval-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{iteration:02d}",
        skill_name=skill_path.name,
        skill_path=str(skill_path.absolute()),
        target=target,
        scenario=scenario,
        iteration=iteration,
        error_type=error_data.get("error_type", "Unknown"),
        error_message=error_data.get("error_message", ""),
        stack_trace=error_data.get("stack_trace", ""),
        exit_code=error_data.get("exit_code", 1),
        stdout=error_data.get("stdout", ""),
        stderr=error_data.get("stderr", ""),
        duration_ms=error_data.get("duration_ms", 0),
        previous_attempts=previous_attempts,
    )


def save_bundle(bundle: ErrorBundle, output_dir: Path) -> Path:
    """Save error bundle to file."""
    bundle_path = output_dir / "bundles" / f"{bundle.bundle_id}.json"
    bundle_path.write_text(bundle.to_json())

    # Also save as 'latest' for easy access
    (output_dir / "bundles" / "latest.json").write_text(bundle.to_json())

    return bundle_path


def invoke_claude_code(bundle: ErrorBundle, skill_path: Path) -> bool:
    """Send error bundle to Claude Code for fixing."""
    prompt = f"""Fix this skill error. Error bundle:

{bundle.to_json()}

The skill is at: {skill_path}

Analyze the error and fix the skill. Focus on:
1. The specific error message and stack trace
2. stdout/stderr output for clues
3. Previous fix attempts that didn't fully work

Make minimal, targeted changes. Commit when done with message:
"fix(skill-eval): iteration {bundle.iteration} - {bundle.error_type}"
"""

    print(f"\n{'='*60}")
    print(f"Iteration {bundle.iteration}: Invoking Claude Code for fix...")
    print(f"Error: {bundle.error_type} - {bundle.error_message[:100]}")
    print(f"{'='*60}\n")

    result = subprocess.run(
        ["claude", "--permission-mode", "acceptEdits", "-p", prompt],
        cwd=skill_path,
    )

    return result.returncode == 0


def generate_report(
    skill_path: Path, result: EvalResult, output_dir: Path
) -> Path:
    """Generate markdown eval report."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    report_path = output_dir / "reports" / f"eval-{timestamp}.md"

    status = "✅ PASS" if result.success else "❌ FAIL"
    status_suffix = f" (after {result.iterations} iterations)" if result.success else f" (max iterations: {result.iterations})"

    iterations_table = "| # | Result | Error | Duration |\n|---|--------|-------|----------|\n"
    for i, bundle in enumerate(result.bundle_history, 1):
        result_icon = "❌" if i < len(result.bundle_history) or not result.success else "✅"
        error = bundle.error_message[:50] if bundle.error_message else "-"
        iterations_table += f"| {i} | {result_icon} | {error} | {bundle.duration_ms}ms |\n"

    if result.success and not result.bundle_history:
        iterations_table += "| 1 | ✅ | - | - |\n"

    report = f"""# Skill Eval Report: {skill_path.name}

**Status**: {status}{status_suffix}
**Duration**: {result.duration_ms}ms
**Skill Path**: {skill_path}
**Generated**: {datetime.now().isoformat()}

## Iterations

{iterations_table}

## Final Error

{result.final_error or "None - skill passed"}

## Changes Made

{chr(10).join(f"- {c}" for c in result.changes_made) or "No changes needed"}

"""

    report_path.write_text(report)
    return report_path


def run_eval_loop(
    skill_path: Path,
    target: str,
    scenario: str,
    max_iterations: int,
    timeout: int,
    headed: bool,
    cwd: Path | None,
    output_dir: Path,
    dry_run: bool,
) -> EvalResult:
    """Main eval loop."""
    start_time = time.time()
    bundle_history: list[ErrorBundle] = []
    changes_made: list[str] = []
    previous_attempts: list[dict] = []

    if dry_run:
        print(f"[DRY RUN] Would eval skill: {skill_path}")
        print(f"[DRY RUN] Target: {target}")
        print(f"[DRY RUN] Scenario: {scenario}")
        print(f"[DRY RUN] Max iterations: {max_iterations}")
        return EvalResult(
            success=True,
            iterations=0,
            duration_ms=0,
            final_error=None,
            changes_made=[],
            bundle_history=[],
        )

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"Iteration {iteration}/{max_iterations}")
        print(f"{'='*60}")

        # Execute skill based on target
        if target.startswith("browser"):
            success, error_data = run_browser_skill(
                skill_path, scenario, timeout, headed or target == "browser-headed"
            )
        else:
            success, error_data = run_shell_skill(skill_path, scenario, timeout, cwd)

        if success:
            print(f"\n✅ Skill passed on iteration {iteration}!")
            return EvalResult(
                success=True,
                iterations=iteration,
                duration_ms=int((time.time() - start_time) * 1000),
                final_error=None,
                changes_made=changes_made,
                bundle_history=bundle_history,
            )

        # Create and save error bundle
        bundle = create_error_bundle(
            skill_path, target, scenario, iteration, error_data, previous_attempts
        )
        bundle_path = save_bundle(bundle, output_dir)
        bundle_history.append(bundle)

        print(f"❌ Failed: {bundle.error_type}")
        print(f"   Bundle saved: {bundle_path}")

        # Invoke Claude Code to fix
        fix_success = invoke_claude_code(bundle, skill_path)

        if fix_success:
            changes_made.append(f"Iteration {iteration}: Fixed {bundle.error_type}")
            previous_attempts.append({
                "iteration": iteration,
                "error": bundle.error_message,
                "fix_applied": f"Claude Code fix for {bundle.error_type}",
            })
        else:
            print(f"⚠️ Claude Code fix failed on iteration {iteration}")

    # Max iterations reached
    final_error = bundle_history[-1].error_message if bundle_history else "Unknown"
    return EvalResult(
        success=False,
        iterations=max_iterations,
        duration_ms=int((time.time() - start_time) * 1000),
        final_error=final_error,
        changes_made=changes_made,
        bundle_history=bundle_history,
    )


def main():
    args = parse_args()

    # Validate skill path
    if not args.skill_path.exists():
        print(f"Error: Skill path not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    # Setup
    output_dir = setup_output_dir(args.skill_path, args.output_dir)
    scenario = args.scenario or detect_scenario(args.skill_path) or "Run skill"
    target = "browser-headed" if args.headed else args.target

    print(f"Skill Eval: {args.skill_path.name}")
    print(f"Target: {target}")
    print(f"Scenario: {scenario}")
    print(f"Max iterations: {args.max_iterations}")

    # Run eval loop
    result = run_eval_loop(
        skill_path=args.skill_path,
        target=target,
        scenario=scenario,
        max_iterations=args.max_iterations,
        timeout=args.timeout,
        headed=args.headed,
        cwd=args.cwd,
        output_dir=output_dir,
        dry_run=args.dry_run,
    )

    # Generate report
    report_path = generate_report(args.skill_path, result, output_dir)
    print(f"\nReport: {report_path}")

    # Exit code
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
