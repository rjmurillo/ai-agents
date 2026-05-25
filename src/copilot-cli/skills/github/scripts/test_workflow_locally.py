#!/usr/bin/env python3
"""Test GitHub Actions workflows locally using nektos/act.

Validates prerequisites, constructs act commands, and provides helpful error messages.

Supported workflows (no AI dependencies):
- pester-tests.yml        : Run Pester unit tests
- validate-paths.yml      : Validate path normalization

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (workflow not found, act execution failed)
    2 - Config error (prerequisites missing)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _check_command_exists(command: str) -> str | None:
    """Check if a command exists. Returns path if found, None otherwise."""
    return shutil.which(command)


def _get_repo_root() -> str:
    """Get the repository root directory."""
    return str(Path(__file__).resolve().parent.parent.parent.parent)


WORKFLOW_MAP = {
    "pester-tests": "pester-tests.yml",
    "validate-paths": "validate-paths.yml",
    "memory-validation": "memory-validation.yml",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test GitHub Actions workflows locally with act.",
    )
    parser.add_argument(
        "--workflow",
        required=True,
        help='Workflow name (without .yml) or full path. E.g., "pester-tests"',
    )
    parser.add_argument(
        "--event",
        default="pull_request",
        help="GitHub event type to simulate (default: pull_request)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate workflow without execution",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output from act",
    )
    parser.add_argument(
        "--job",
        default="",
        help="Specific job name to run",
    )
    parser.add_argument(
        "--secrets",
        default="",
        help='JSON object of secrets, e.g. \'{"GITHUB_TOKEN":"ghp_..."}\'',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print("[INFO] Checking prerequisites...")

    # Check for act
    act_path = _check_command_exists("act")
    if not act_path:
        print("[ERROR] act not found. Install act to enable local workflow testing.")
        print()
        print("Installation instructions:")
        print("  macOS:       brew install act")
        print("  Windows:     Download from https://github.com/nektos/act/releases")
        print("  Linux:       Download from https://github.com/nektos/act/releases")
        print("  GitHub CLI:  gh extension install https://github.com/nektos/gh-act")
        print()
        print("See: https://nektosact.com/installation/index.html")
        return 2

    act_version = subprocess.run(
        ["act", "--version"], capture_output=True, text=True, check=False,
    )
    print(f"[SUCCESS] act found: {act_version.stdout.strip()}")

    # Check for Docker
    docker_path = _check_command_exists("docker")
    if not docker_path:
        print("[ERROR] Docker not found. act requires Docker to run workflows.")
        print()
        print("Install Docker:")
        print("  macOS/Windows: https://www.docker.com/products/docker-desktop")
        print("  Linux:         https://docs.docker.com/engine/install/")
        return 2

    docker_result = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False,
    )
    if docker_result.returncode != 0:
        print("[ERROR] Docker daemon is not running. Start Docker and try again.")
        return 2
    print("[SUCCESS] Docker is running")

    # Resolve workflow path
    repo_root = _get_repo_root()
    workflows_dir = os.path.join(repo_root, ".github", "workflows")

    workflow_path: str | None = None
    workflow = args.workflow

    if workflow.endswith(".yml") or workflow.endswith(".yaml"):
        if os.path.exists(workflow):
            workflow_path = workflow
        else:
            candidate = os.path.join(workflows_dir, workflow)
            if os.path.exists(candidate):
                workflow_path = candidate
    elif workflow in WORKFLOW_MAP:
        workflow_path = os.path.join(workflows_dir, WORKFLOW_MAP[workflow])
    else:
        workflow_path = os.path.join(workflows_dir, f"{workflow}.yml")

    if not workflow_path or not os.path.exists(workflow_path):
        print(f"[ERROR] Workflow file not found: {workflow}")
        print()
        print("Available workflows:")
        for key in sorted(WORKFLOW_MAP.keys()):
            print(f"  - {key}")
        print()
        print("Unsupported workflows (require AI infrastructure or Copilot CLI):")
        print("  - ai-session-protocol (requires Copilot CLI with BOT_PAT)")
        print("  - ai-pr-quality-gate (requires Copilot CLI with BOT_PAT)")
        print("  - ai-spec-validation (requires Copilot CLI with BOT_PAT)")
        return 1

    print(f"[INFO] Workflow: {workflow_path}")

    # Build act command
    act_args = [args.event, "-W", workflow_path]

    if args.job:
        act_args.extend(["-j", args.job])

    if args.dry_run:
        act_args.append("-n")
        print("[INFO] Dry-run mode: validating workflow without execution")

    if args.verbose:
        act_args.append("-v")

    # Parse secrets
    secrets: dict[str, str] = {}
    if args.secrets:
        try:
            secrets = json.loads(args.secrets)
        except json.JSONDecodeError:
            print("[ERROR] Invalid JSON for --secrets parameter", file=sys.stderr)
            return 1

    for key, value in secrets.items():
        act_args.extend(["-s", f"{key}={value}"])

    # Try to get GITHUB_TOKEN from gh CLI if not provided
    if "GITHUB_TOKEN" not in secrets:
        gh_path = _check_command_exists("gh")
        if gh_path:
            token_result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, check=False,
            )
            if token_result.returncode == 0 and token_result.stdout.strip():
                act_args.extend(["-s", f"GITHUB_TOKEN={token_result.stdout.strip()}"])
                print("[INFO] Using GITHUB_TOKEN from gh CLI")

    # Execute act
    print(f"[INFO] Running: act {' '.join(act_args)}")
    print()

    result = subprocess.run(
        ["act", *act_args],
        cwd=repo_root,
        check=False,
    )

    if result.returncode == 0:
        print()
        print("[SUCCESS] Workflow execution completed successfully")
        return 0

    print()
    print(f"[ERROR] Workflow execution failed with exit code {result.returncode}")
    print()
    print("Troubleshooting tips:")
    print("  1. Check Docker logs: docker ps -a | grep act-")
    print("  2. Run with --verbose for detailed output")
    print("  3. Use --dry-run to validate workflow syntax")
    print("  4. Ensure Docker has sufficient resources")
    print()
    print("Common issues:")
    print("  - Missing dependencies: Use catthehacker/ubuntu:act-latest image")
    print("  - Windows-specific code: act uses Linux containers")
    print("  - Secrets not available: Pass via --secrets parameter")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
