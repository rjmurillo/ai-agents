#!/usr/bin/env python3
"""Test GitHub Actions workflows locally with act.

Simplifies local workflow testing by providing a CLI interface
to nektos/act. Validates prerequisites, constructs act commands,
and provides helpful error messages.

Exit codes (ADR-035):
    0 = Success
    1 = Workflow execution failed or workflow not found
    2 = Prerequisites not met (act/Docker not installed)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

WORKFLOW_MAP = {
    "pester-tests": "pester-tests.yml",
    "validate-paths": "validate-paths.yml",
    "memory-validation": "memory-validation.yml",
}


def _check_prerequisites() -> list[str]:
    """Check that act and Docker are available. Return list of errors."""
    errors = []
    if not shutil.which("act"):
        errors.append(
            "act not found. Install: brew install act, "
            "choco install act-cli, or download from "
            "https://github.com/nektos/act/releases"
        )
    if not shutil.which("docker"):
        errors.append(
            "Docker not found. Install: "
            "https://www.docker.com/products/docker-desktop"
        )
    else:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append("Docker daemon is not running. Start Docker and retry.")
    return errors


def _resolve_workflow_path(workflow: str, repo_root: str) -> str | None:
    """Resolve workflow name or path to absolute file path."""
    workflows_dir = os.path.join(repo_root, ".github", "workflows")

    if workflow.endswith(".yml") or workflow.endswith(".yaml"):
        if os.path.isfile(workflow):
            return os.path.abspath(workflow)
        candidate = os.path.join(workflows_dir, workflow)
        if os.path.isfile(candidate):
            return candidate
        return None

    if workflow in WORKFLOW_MAP:
        candidate = os.path.join(workflows_dir, WORKFLOW_MAP[workflow])
        if os.path.isfile(candidate):
            return candidate
        return None

    candidate = os.path.join(workflows_dir, f"{workflow}.yml")
    if os.path.isfile(candidate):
        return candidate
    return None


def _get_gh_token() -> str | None:
    """Try to get GITHUB_TOKEN from gh CLI."""
    if not shutil.which("gh"):
        return None
    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def test_workflow_locally(
    workflow: str,
    event: str = "pull_request",
    dry_run: bool = False,
    verbose: bool = False,
    job: str = "",
    secrets: dict | None = None,
) -> dict:
    """Run a GitHub Actions workflow locally with act.

    Args:
        workflow: Workflow name or path.
        event: GitHub event type.
        dry_run: Validate without executing.
        verbose: Enable verbose output.
        job: Specific job name to run.
        secrets: Dict of secrets to pass.

    Returns:
        Dict with execution result.
    """
    errors = _check_prerequisites()
    if errors:
        return {
            "Success": False,
            "Errors": errors,
            "ExitCode": 2,
        }

    # Find repo root
    git_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    repo_root = git_result.stdout.strip() if git_result.returncode == 0 else os.getcwd()

    workflow_path = _resolve_workflow_path(workflow, repo_root)
    if not workflow_path:
        available = list(WORKFLOW_MAP.keys())
        return {
            "Success": False,
            "Error": f"Workflow file not found: {workflow}",
            "AvailableWorkflows": available,
            "ExitCode": 1,
        }

    act_args = ["act", event, "-W", workflow_path]

    if job:
        act_args.extend(["-j", job])
    if dry_run:
        act_args.append("-n")
    if verbose:
        act_args.append("-v")

    secrets = secrets or {}
    if "GITHUB_TOKEN" not in secrets:
        token = _get_gh_token()
        if token:
            secrets["GITHUB_TOKEN"] = token

    for key, value in secrets.items():
        act_args.extend(["-s", f"{key}={value}"])

    result = subprocess.run(
        act_args,
        cwd=repo_root,
    )

    return {
        "Success": result.returncode == 0,
        "Workflow": workflow_path,
        "Event": event,
        "DryRun": dry_run,
        "ExitCode": result.returncode,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test GitHub Actions workflows locally with act"
    )
    parser.add_argument("--workflow", required=True, help="Workflow name or path")
    parser.add_argument(
        "--event", default="pull_request",
        help="GitHub event type",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate without executing",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument("--job", default="", help="Specific job to run")
    parser.add_argument(
        "--secret", action="append", default=[],
        help="Secret in KEY=VALUE format (repeatable)",
    )
    args = parser.parse_args()

    secrets = {}
    for s in args.secret:
        if "=" in s:
            key, value = s.split("=", 1)
            secrets[key] = value

    output = test_workflow_locally(
        args.workflow, args.event, args.dry_run,
        args.verbose, args.job, secrets,
    )

    print(json.dumps(output, indent=2))

    exit_code = output.get("ExitCode", 1)
    if output["Success"]:
        print("Workflow execution completed successfully", file=sys.stderr)
    else:
        print(
            f"Workflow failed with exit code {exit_code}",
            file=sys.stderr,
        )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
